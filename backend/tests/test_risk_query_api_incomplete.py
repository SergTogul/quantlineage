"""API tests for incomplete OpenAI responses on POST /api/v1/risk/query."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from openai.types.responses import Response, ResponseFunctionToolCall

from app.ai.config import AISettings
from app.ai.errors import OpenAIIncompleteResponseError
from app.ai.openai_model import OpenAIRiskAssistantModel
from app.api.schemas import RiskQueryRequest
from app.domain.models import Portfolio
from app.main import app
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
)


@dataclass
class _FakeResponses:
    responses: list[Any]
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._index >= len(self.responses):
            raise AssertionError("FakeResponses queue exhausted")
        item = self.responses[self._index]
        self._index += 1
        if isinstance(item, BaseException):
            raise item
        return item


@dataclass
class _ScriptedModel:
    """Raises then returns, one complete() call at a time."""

    outcomes: list[Any]
    requests: list[RiskAssistantModelRequest] = field(default_factory=list)
    _index: int = 0

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        self.requests.append(request)
        if self._index >= len(self.outcomes):
            raise AssertionError("ScriptedModel outcomes exhausted")
        item = self.outcomes[self._index]
        self._index += 1
        if isinstance(item, BaseException):
            raise item
        return item


def _incomplete_sdk_response() -> Response:
    return Response(
        id="resp_incomplete",
        created_at=0,
        model="gpt-test-model",
        object="response",
        output=[],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
    )


def _contributors_sdk_response() -> Response:
    return Response(
        id="resp_ok",
        created_at=0,
        model="gpt-test-model",
        object="response",
        output=[
            ResponseFunctionToolCall(
                type="function_call",
                call_id="call_contrib",
                name="get_contributors",
                arguments="{}",
            )
        ],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )


def _openai_settings() -> AISettings:
    return AISettings(
        provider="openai",
        openai_model="gpt-test-model",
        timeout_seconds=30.0,
        max_output_tokens=256,
        max_tool_rounds=1,
    )


def _post_top_contributors(client: TestClient):
    portfolio = client.get("/api/v1/portfolio").json()
    return client.post(
        "/api/v1/risk/query",
        json=RiskQueryRequest(
            portfolio=Portfolio.model_validate(portfolio),
            question="Top contributors?",
        ).model_dump(mode="json"),
    )


@pytest.fixture
def openai_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-api-incomplete")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-model")
    monkeypatch.setenv("AI_ASSISTANT_LOOP", "router")
    monkeypatch.setattr(
        "openai.OpenAI",
        MagicMock(return_value=SimpleNamespace(close=MagicMock())),
    )


def test_api_incomplete_does_not_consume_queued_success(openai_env) -> None:
    fake = _FakeResponses(responses=[_incomplete_sdk_response(), _contributors_sdk_response()])
    model = OpenAIRiskAssistantModel(SimpleNamespace(responses=fake), _openai_settings())

    with TestClient(app) as client:
        client.app.state.risk_assistant_model = model
        client.app.state.portfolio_service.risk_assistant_model = model
        response = _post_top_contributors(client)

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "contributors"
    assert body["tool_name"] == "get_contributors"
    assert body["data"]["assistant"]["mode"] == "fallback"
    assert body["data"]["assistant"]["fallback"] is True
    assert "Top risk contributors" in body["answer"]
    assert len(fake.calls) == 1


def test_api_incomplete_exhausted_falls_back_with_200(openai_env) -> None:
    fake = _FakeResponses(
        responses=[_incomplete_sdk_response(), _incomplete_sdk_response()]
    )
    model = OpenAIRiskAssistantModel(SimpleNamespace(responses=fake), _openai_settings())

    with TestClient(app) as client:
        client.app.state.risk_assistant_model = model
        client.app.state.portfolio_service.risk_assistant_model = model
        response = _post_top_contributors(client)

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "contributors"
    assert body["tool_name"] == "get_contributors"
    assert body["data"]["assistant"]["mode"] == "fallback"
    assert body["data"]["assistant"]["fallback"] is True
    assert "Top risk contributors" in body["answer"]
    assert len(fake.calls) == 1


def test_api_scripted_incomplete_before_tool_falls_back_with_200(openai_env) -> None:
    model = _ScriptedModel(
        outcomes=[
            OpenAIIncompleteResponseError("OpenAI response status was 'incomplete'."),
        ]
    )

    with TestClient(app) as client:
        client.app.state.risk_assistant_model = model
        client.app.state.portfolio_service.risk_assistant_model = model
        response = _post_top_contributors(client)

    assert response.status_code == 200
    body = response.json()
    assert body["tool_name"] == "get_contributors"
    assert body["data"]["assistant"]["fallback"] is True
    assert len(model.requests) == 1
