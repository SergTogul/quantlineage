"""C08 — provider-neutral conversation_id (network-free)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.config import AISettings
from app.ai.conversations import (
    CONVERSATION_MAX_TURNS,
    CONVERSATION_TTL_SECONDS,
    ConversationAccessDenied,
    ConversationNotFound,
    InMemoryConversationRepository,
)
from app.api.schemas.transport import RiskQueryRequest, RiskQueryResponse
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
)
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService


class _ContextAwareGreeksModel:
    """Selects Greeks from the current question plus prior conversation turns."""

    def __init__(self) -> None:
        self.complete_requests: list[RiskAssistantModelRequest] = []
        self.complete_count = 0
        self.continue_count = 0

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        self.complete_count += 1
        self.complete_requests.append(request)
        question = request.question.lower()
        prior_options = any(
            "option" in str(turn.get("question", "")).lower()
            or bool((turn.get("tool_args") or {}).get("options_only"))
            for turn in request.conversation_history
        )
        if "gamma" in question:
            greek = "gamma"
            options_only = prior_options or "option" in question
        else:
            greek = "delta"
            options_only = "option" in question
        return RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_POSITION_GREEKS,
            tool_args={"greek": greek, "options_only": options_only},
            intent="position_greeks",
            tool_call_id=f"call_{greek}",
            provider_response_id=f"resp_{greek}",
        )

    def continue_after_tools(self, **_kwargs: Any) -> RiskAssistantModelResponse:
        self.continue_count += 1
        return RiskAssistantModelResponse(
            proposed_answer="Position Greeks were calculated by QuantLineage tools.",
            intent="final",
            provider_response_id="resp_final",
        )


def _settings() -> AISettings:
    return AISettings(
        provider="openai",
        openai_model="gpt-test-model",
        timeout_seconds=30.0,
        max_output_tokens=512,
        max_tool_rounds=2,
        max_tool_calls=1,
        assistant_loop="conversational",
    )


def _service(model, *, repo=None) -> PortfolioService:
    return PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
        risk_assistant_model=model,
        ai_settings=_settings(),
        conversation_repo=repo if repo is not None else InMemoryConversationRepository(),
    )


def test_risk_query_request_accepts_optional_conversation_id() -> None:
    body = RiskQueryRequest.model_validate(
        {
            "portfolio": SAMPLE_PORTFOLIO.model_dump(mode="json"),
            "question": "What is 99% VaR?",
        }
    )
    assert body.conversation_id is None
    with_id = RiskQueryRequest.model_validate(
        {
            "portfolio": SAMPLE_PORTFOLIO.model_dump(mode="json"),
            "question": "What about gamma?",
            "conversation_id": "conv_test",
        }
    )
    assert with_id.conversation_id == "conv_test"


def test_first_turn_creates_and_returns_application_conversation_id() -> None:
    model = _ContextAwareGreeksModel()
    service = _service(model)

    response = service.query(
        SAMPLE_PORTFOLIO,
        "Which options have the largest delta?",
        principal="alice",
    )

    conversation_id = response.data["conversation_id"]
    assert isinstance(conversation_id, str) and conversation_id
    assert "resp_" not in conversation_id
    blob = response.model_dump(mode="json")
    assert "resp_delta" not in str(blob)
    assert "provider_response_id" not in str(blob)
    assert response.tool_name == "get_position_greeks"


def test_follow_up_gamma_resolves_from_prior_options_delta_context() -> None:
    model = _ContextAwareGreeksModel()
    service = _service(model)

    first = service.query(
        SAMPLE_PORTFOLIO,
        "Which options have the largest delta?",
        principal="alice",
    )
    conversation_id = first.data["conversation_id"]
    first_ids = {row["position_id"] for row in first.data["tool_result"]["positions"]}

    second = service.query(
        SAMPLE_PORTFOLIO,
        "What about gamma?",
        conversation_id=conversation_id,
        principal="alice",
    )

    assert second.data["conversation_id"] == conversation_id
    follow_up = model.complete_requests[-1]
    assert follow_up.question == "What about gamma?"
    assert follow_up.conversation_history
    assert follow_up.conversation_history[0]["question"] == (
        "Which options have the largest delta?"
    )
    assert follow_up.conversation_history[0]["tool_name"] == "get_position_greeks"
    assert follow_up.conversation_history[0]["tool_args"]["options_only"] is True
    assert "resp_delta" not in str(follow_up.model_dump(mode="json"))
    assert second.tool_name == "get_position_greeks"
    assert second.data["tool_result"]["greek"] == "gamma"
    assert second.data["tool_result"]["options_only"] is True
    for row in second.data["tool_result"]["positions"]:
        assert "option" in row["instrument_type"]
        assert row["position_id"] not in {"eq-spy", "eq-msft", "eq-nvda", "eq-aapl"}
    assert first_ids  # prior delta ranking existed
    RiskQueryResponse.model_validate(second.model_dump(mode="json"))


def test_cross_principal_conversation_access_fails_closed() -> None:
    model = _ContextAwareGreeksModel()
    service = _service(model)
    first = service.query(
        SAMPLE_PORTFOLIO,
        "Which options have the largest delta?",
        principal="alice",
    )
    conversation_id = first.data["conversation_id"]

    with pytest.raises(ConversationAccessDenied):
        service.query(
            SAMPLE_PORTFOLIO,
            "What about gamma?",
            conversation_id=conversation_id,
            principal="bob",
        )

    with pytest.raises(ConversationNotFound):
        service.query(
            SAMPLE_PORTFOLIO,
            "What about gamma?",
            conversation_id="missing-conversation",
            principal="alice",
        )


def test_conversation_repo_records_tool_turns_without_secrets_or_cot() -> None:
    repo = InMemoryConversationRepository()
    record = repo.create(principal="alice")
    repo.append_turn(
        record.id,
        principal="alice",
        question="Which options have the largest delta?",
        answer="delta ranking",
        tool_name="get_position_greeks",
        tool_args={"greek": "delta", "options_only": True},
        tool_result={"greek": "delta", "positions": []},
        provider_response_id="resp_secret",
    )
    loaded = repo.get(record.id, principal="alice")
    dumped = loaded.model_dump(mode="json")
    assert dumped["turns"][0]["tool_name"] == "get_position_greeks"
    assert "resp_secret" not in str(dumped)
    assert "provider_response_id" not in dumped
    assert "chain_of_thought" not in str(dumped)
    with pytest.raises(ValidationError):
        type(loaded).model_validate({**dumped, "provider_response_id": "resp_secret"})


def test_conversation_expiry_and_delete_restart() -> None:
    clock = {"now": datetime(2026, 9, 20, tzinfo=UTC)}
    repo = InMemoryConversationRepository(
        ttl_seconds=60,
        now=lambda: clock["now"],
    )
    record = repo.create(principal="alice")
    assert CONVERSATION_TTL_SECONDS >= 60
    assert CONVERSATION_MAX_TURNS >= 4

    clock["now"] = clock["now"] + timedelta(seconds=61)
    with pytest.raises(ConversationNotFound):
        repo.get(record.id, principal="alice")

    fresh = repo.create(principal="alice")
    repo.delete(fresh.id, principal="alice")
    with pytest.raises(ConversationNotFound):
        repo.get(fresh.id, principal="alice")


def test_conversation_history_is_bounded() -> None:
    repo = InMemoryConversationRepository()
    record = repo.create(principal="alice")
    for index in range(CONVERSATION_MAX_TURNS + 3):
        repo.append_turn(
            record.id,
            principal="alice",
            question=f"q{index}",
            answer=f"a{index}",
            tool_name="get_var_es",
            tool_args={},
            tool_result={"n": index},
        )
    loaded = repo.get(record.id, principal="alice")
    assert len(loaded.turns) == CONVERSATION_MAX_TURNS
    assert loaded.turns[0].question == "q3"
    assert loaded.turns[-1].question == f"q{CONVERSATION_MAX_TURNS + 2}"


def test_compose_external_worker_two_turn_query_keeps_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C16: QUANTLINEAGE_EXTERNAL_WORKER=1 still serves interactive chat."""
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("QUANTLINEAGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        first = client.post(
            "/api/v1/risk/query",
            json={"portfolio": book, "question": "What is 99% VaR?"},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        conversation_id = body["data"]["conversation_id"]
        assert conversation_id.startswith("conv_")
        blob = json.dumps(body)
        assert "OPENAI_API_KEY" not in blob
        assert "previous_response_id" not in blob

        second = client.post(
            "/api/v1/risk/query",
            json={
                "portfolio": book,
                "question": "What about ES?",
                "conversation_id": conversation_id,
            },
        )
        assert second.status_code == 200, second.text
        follow = second.json()
        assert follow["data"]["conversation_id"] == conversation_id
        follow_blob = json.dumps(follow)
        assert "OPENAI_API_KEY" not in follow_blob
        assert "sk-" not in follow_blob.lower()
