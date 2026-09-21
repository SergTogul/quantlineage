"""Provider-neutral application conversation state for Risk Query.

The public contract is an application ``conversation_id``. OpenAI
``previous_response_id`` may be stored adapter-side and is never returned
to clients.

Local/demo and the current shared FastAPI process use
:class:`InMemoryConversationRepository`. That store does **not** survive
process restarts; SQL persistence is not wired in this slice. Cross-principal
access always fails closed.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

CONVERSATION_MAX_TURNS = 8
CONVERSATION_TTL_SECONDS = 24 * 60 * 60
CONVERSATION_MAX_CONTEXT_BYTES = 2048
CONVERSATION_MAX_PER_PRINCIPAL = 8
CONVERSATION_MAX_TOOL_ARGS_BYTES = 256
LOCAL_PRINCIPAL = "demo"


class ConversationAccessDenied(PermissionError):
    """Caller is not the conversation owner."""


class ConversationNotFound(LookupError):
    """Unknown, expired, or deleted conversation id."""


class ConversationTurn(BaseModel):
    """One user/assistant exchange recorded without provider ids or CoT."""

    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_result: dict[str, Any] | None = None
    created_at: datetime


class ConversationRecord(BaseModel):
    """Client-safe conversation snapshot (no provider response ids)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    principal: str
    turns: list[ConversationTurn] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


def _normalize_principal(principal: str | None) -> str:
    text = (principal or "").strip()
    return text or LOCAL_PRINCIPAL


def _utcnow() -> datetime:
    return datetime.now(UTC)


def conversation_history_for_model(record: ConversationRecord) -> list[dict[str, Any]]:
    """Bounded prior context for a follow-up model turn (no provider ids)."""
    history: list[dict[str, Any]] = []
    for turn in record.turns:
        history.append(
            {
                "question": turn.question,
                "answer": turn.answer,
                "tool_name": turn.tool_name,
                "tool_args": _clip_tool_args(turn.tool_args),
            }
        )
    while history and _history_size(history) > CONVERSATION_MAX_CONTEXT_BYTES:
        history.pop(0)
    if history and _history_size(history) > CONVERSATION_MAX_CONTEXT_BYTES:
        history[-1] = _clip_history_item(history[-1], CONVERSATION_MAX_CONTEXT_BYTES)
    return history


def _clip_tool_args(tool_args: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(tool_args or {})
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) <= CONVERSATION_MAX_TOOL_ARGS_BYTES:
        return payload
    return {"_truncated": True}


def _history_size(history: list[dict[str, Any]]) -> int:
    return len(json.dumps(history, default=str).encode("utf-8"))


def _clip_history_item(item: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    clipped = dict(item)
    answer = clipped.get("answer")
    if isinstance(answer, str):
        budget = max(max_bytes // 2, 32)
        encoded = answer.encode("utf-8")
        if len(encoded) > budget:
            clipped["answer"] = encoded[:budget].decode("utf-8", errors="ignore")
    clipped["tool_args"] = _clip_tool_args(clipped.get("tool_args"))
    return clipped


class ConversationRepository(Protocol):
    def create(self, principal: str | None) -> ConversationRecord: ...

    def get(self, conversation_id: str, *, principal: str | None) -> ConversationRecord: ...

    def append_turn(
        self,
        conversation_id: str,
        *,
        principal: str | None,
        question: str,
        answer: str | None,
        tool_name: str | None,
        tool_args: dict[str, Any] | None = None,
        tool_result: dict[str, Any] | None = None,
        provider_response_id: str | None = None,
    ) -> ConversationRecord: ...

    def delete(self, conversation_id: str, *, principal: str | None) -> None: ...


class InMemoryConversationRepository:
    """Process-local conversation store. Does not survive restarts."""

    SURVIVES_RESTARTS = False

    def __init__(
        self,
        *,
        ttl_seconds: int = CONVERSATION_TTL_SECONDS,
        max_turns: int = CONVERSATION_MAX_TURNS,
        max_conversations: int = CONVERSATION_MAX_PER_PRINCIPAL,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl_seconds = max(int(ttl_seconds), 1)
        self._max_turns = max(int(max_turns), 1)
        self._max_conversations = max(int(max_conversations), 1)
        self._now = now or _utcnow
        self._lock = threading.RLock()
        self._records: dict[str, ConversationRecord] = {}
        self._provider_response_ids: dict[str, str] = {}

    def create(self, principal: str | None) -> ConversationRecord:
        owner = _normalize_principal(principal)
        now = self._now()
        record = ConversationRecord(
            id=f"conv_{uuid.uuid4().hex}",
            principal=owner,
            turns=[],
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        with self._lock:
            self._reclaim_expired_unlocked()
            self._evict_for_capacity_unlocked(owner)
            self._records[record.id] = record
        return record.model_copy(deep=True)

    def get(self, conversation_id: str, *, principal: str | None) -> ConversationRecord:
        with self._lock:
            self._reclaim_expired_unlocked()
            return self._load_owned(conversation_id, principal).model_copy(deep=True)

    def append_turn(
        self,
        conversation_id: str,
        *,
        principal: str | None,
        question: str,
        answer: str | None,
        tool_name: str | None,
        tool_args: dict[str, Any] | None = None,
        tool_result: dict[str, Any] | None = None,
        provider_response_id: str | None = None,
    ) -> ConversationRecord:
        with self._lock:
            self._reclaim_expired_unlocked()
            record = self._load_owned(conversation_id, principal)
            now = self._now()
            turn = ConversationTurn(
                question=question,
                answer=answer,
                tool_name=tool_name,
                tool_args=dict(tool_args or {}),
                tool_result=tool_result,
                created_at=now,
            )
            turns = list(record.turns) + [turn]
            if len(turns) > self._max_turns:
                turns = turns[-self._max_turns :]
            updated = record.model_copy(
                update={
                    "turns": turns,
                    "updated_at": now,
                    "expires_at": now + timedelta(seconds=self._ttl_seconds),
                }
            )
            self._records[conversation_id] = updated
            if provider_response_id:
                self._provider_response_ids[conversation_id] = provider_response_id
            return updated.model_copy(deep=True)

    def delete(self, conversation_id: str, *, principal: str | None) -> None:
        with self._lock:
            self._load_owned(conversation_id, principal)
            self._records.pop(conversation_id, None)
            self._provider_response_ids.pop(conversation_id, None)

    def reclaim_expired(self) -> int:
        with self._lock:
            return self._reclaim_expired_unlocked()

    def peek_provider_response_id(
        self, conversation_id: str, *, principal: str | None
    ) -> str | None:
        with self._lock:
            self._load_owned(conversation_id, principal)
            return self._provider_response_ids.get(conversation_id)

    def _load_owned(
        self, conversation_id: str, principal: str | None
    ) -> ConversationRecord:
        record = self._records.get(conversation_id)
        if record is None:
            raise ConversationNotFound(conversation_id)
        if record.expires_at <= self._now():
            self._records.pop(conversation_id, None)
            self._provider_response_ids.pop(conversation_id, None)
            raise ConversationNotFound(conversation_id)
        owner = _normalize_principal(principal)
        if record.principal != owner:
            raise ConversationAccessDenied(conversation_id)
        return record

    def _reclaim_expired_unlocked(self) -> int:
        now = self._now()
        expired = [
            conversation_id
            for conversation_id, record in self._records.items()
            if record.expires_at <= now
        ]
        for conversation_id in expired:
            self._records.pop(conversation_id, None)
            self._provider_response_ids.pop(conversation_id, None)
        return len(expired)

    def _evict_for_capacity_unlocked(self, owner: str) -> None:
        owned = [
            record
            for record in self._records.values()
            if record.principal == owner
        ]
        while len(owned) >= self._max_conversations:
            oldest = min(owned, key=lambda record: (record.updated_at, record.created_at, record.id))
            self._records.pop(oldest.id, None)
            self._provider_response_ids.pop(oldest.id, None)
            owned = [
                record
                for record in self._records.values()
                if record.principal == owner
            ]
