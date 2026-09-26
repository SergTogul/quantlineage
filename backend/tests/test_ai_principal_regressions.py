"""Exercise the real SDK, adapter, assistant and HTTP boundary without network."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI

from app.ai import budget
from app.ai.assistant import BoundedRiskAssistant, RiskAssistantRequest
from app.ai.config import AISettings
from app.ai.errors import OpenAIIncompleteResponseError, OpenAITimeoutError, sanitize_client_data
from app.ai.openai_model import OpenAIRiskAssistantModel, _parse_sdk_response
from app.api.deps import get_portfolio_service
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.query import RiskAssistantModelRequest
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService


def settings():
    return AISettings(provider="openai", openai_model="test", timeout_seconds=30,
                      max_output_tokens=512, max_tool_rounds=2, max_tool_calls=1,
                      assistant_loop="conversational")


def response(output, status="completed"):
    return {"id": "resp_test", "created_at": 0, "model": "test", "object": "response",
            "status": status, "output": output, "parallel_tool_calls": False,
            "tool_choice": "auto", "tools": []}


def message(text):
    return {"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


@pytest.mark.parametrize("attack", [None, "VaR is $50 million.", "No limits are breached.",
                                  "Delta for position B is 50.", "unknown", "extra"])
def test_sdk_to_http_claim_selection_and_attacks(attack):
    calls = []
    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(200, json=response([{
                "type": "function_call", "id": "fc1", "call_id": "call1",
                "name": "get_var_es", "arguments": "{}",
            }]))
        assert body["text"]["format"]["type"] == "json_schema"
        envelope = json.loads(body["input"][0]["output"])
        assert envelope["result"]["methods"]
        key, _fact = next((key, fact) for key, fact in envelope["claims"].items()
                         if fact["metric"] == "var")
        if attack == "unknown":
            text = json.dumps({"claim_ids": ["claim_forged"]})
        elif attack == "extra":
            text = json.dumps({"claim_ids": [key], "answer": "No limits are breached."})
        else:
            text = attack or json.dumps({"claim_ids": [key]})
        return httpx.Response(200, json=response([message(text)]))

    with OpenAI(api_key="test-key", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
        model = OpenAIRiskAssistantModel(sdk, settings())
        service = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=1, observations=20),
                                   risk_assistant_model=model, ai_settings=settings())
        with TestClient(app) as client:
            app.dependency_overrides[get_portfolio_service] = lambda: service
            try:
                result = client.post("/api/v1/risk/query", json={
                    "portfolio": SAMPLE_PORTFOLIO.model_dump(mode="json"), "question": "Show VaR",
                })
            finally:
                app.dependency_overrides.pop(get_portfolio_service, None)
    assert result.status_code == 200, result.text
    data = result.json()
    assert len(calls) == 2
    assert data["data"]["investigation"]["narration_grounded"] is (attack is None)
    if attack is None:
        expected = data["data"]["tool_result"]["methods"][0]["var"]
        assert f"- var: {expected:.12g} currency" in data["answer"]
    else:
        assert attack not in data["answer"]


def test_numeric_continuation_is_candidate_but_initial_numeric_text_is_not():
    item = SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="VaR is 50.")])
    raw = SimpleNamespace(id="r", status="completed", output=[item])
    assert _parse_sdk_response(raw, allow_final_text=True).proposed_answer == "VaR is 50."
    assert _parse_sdk_response(raw).requires_clarification


@pytest.mark.parametrize("status", ["incomplete", "failed"])
def test_incomplete_adapter_uses_one_actual_sdk_request(status):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=response([], status))
    with OpenAI(api_key="test-key", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
        model = OpenAIRiskAssistantModel(sdk, settings())
        with pytest.raises(OpenAIIncompleteResponseError):
            model.complete(RiskAssistantModelRequest(question="VaR", tools=[]))
    assert len(calls) == 1


def test_shared_deadline_reduces_second_call_timeout(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(budget, "monotonic", lambda: now[0])
    calls = []
    class Fake:
        def create(self, **kwargs):
            calls.append(kwargs)
            now[0] += 8
            if len(calls) == 1:
                return SimpleNamespace(status="completed", id="r1", output=[SimpleNamespace(
                    type="function_call", name="get_var_es", arguments="{}", call_id="c1")])
            return SimpleNamespace(status="completed", id="r2", output=[SimpleNamespace(
                type="message", content=[SimpleNamespace(type="output_text", text='{"claim_ids": []}')])])
    model = OpenAIRiskAssistantModel(SimpleNamespace(responses=Fake()), settings())
    result = BoundedRiskAssistant(model, lambda *_: {"var": 50}).run(
        RiskAssistantRequest(question="VaR", tools=[], max_rounds=2, timeout_seconds=20))
    assert result.rounds_used == 2
    assert [call["timeout"] for call in calls] == [20, 12]


def test_expired_tool_result_prevents_continuation(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(budget, "monotonic", lambda: now[0])
    class Fake:
        def complete(self, request):
            from app.risk.query import RiskAssistantModelResponse
            return RiskAssistantModelResponse(tool_name="get_var_es", tool_args={})
        def continue_after_tools(self, **kwargs):
            raise AssertionError("Deadline must prevent continuation")
    def execute(*args):
        now[0] = 21
        return {"var": 50}
    with pytest.raises(OpenAITimeoutError):
        BoundedRiskAssistant(Fake(), execute).run(
            RiskAssistantRequest(question="VaR", tools=[], timeout_seconds=20))
    assert budget.remaining_seconds(30) == 30  # request-local context restored


def test_deadline_before_tool_does_not_start_deterministic_fallback(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(budget, "monotonic", lambda: now[0])
    class Fake:
        def complete(self, request):
            from app.risk.query import RiskAssistantModelResponse
            now[0] = 31
            return RiskAssistantModelResponse(tool_name="get_var_es")
        def continue_after_tools(self, **kwargs):
            raise AssertionError("No continuation allowed")
    service = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=1, observations=20),
                               risk_assistant_model=Fake(), ai_settings=settings())
    def forbidden(*args, **kwargs):
        raise AssertionError("Expired request must not start fallback tool")
    service.var_report = forbidden
    result = service.query(SAMPLE_PORTFOLIO, "Show VaR")
    assert "deadline exceeded" in result.answer
    assert result.tool_name is None


def test_factory_disables_sdk_retries_on_http_503(monkeypatch):
    from app.ai.errors import OpenAIServerError
    from app.ai.factory import build_risk_assistant_resources

    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "unavailable"}})
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: OpenAI(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    resources = build_risk_assistant_resources(settings=settings())
    try:
        with pytest.raises(OpenAIServerError):
            resources.model.complete(RiskAssistantModelRequest(question="VaR", tools=[]))
    finally:
        resources.close()
    assert len(calls) == 1


def test_client_data_redaction_is_recursive_and_preserves_risk_values():
    payload = {"var": 50, "nested": [{"api_key": "sk-secret-value-12345678",
                                       "system": "internal prompt", "note": "Bearer abc.def"}]}
    sanitized = sanitize_client_data(payload)
    assert sanitized["var"] == 50
    assert sanitized["nested"][0]["api_key"] == "[REDACTED]"
    assert sanitized["nested"][0]["system"] == "[REDACTED]"
    assert "Bearer" not in sanitized["nested"][0]["note"]
