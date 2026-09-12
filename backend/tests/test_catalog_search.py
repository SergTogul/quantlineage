"""G2: instrument catalog merge + GET /instruments/search (mocked provider, no live network)."""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.instruments import get_search_provider
from app.main import app
from app.market.catalog import (
    WAVE_A_UNIVERSE,
    CatalogRecord,
    search_catalog,
)
from app.market.ingestion.errors import (
    AuthorizationError,
    MalformedResponseError,
    NotFoundError,
    RateLimitedError,
    UnavailableError,
)
from app.market.ingestion.models import InstrumentCandidate


class FakeSearchProvider:
    def __init__(
        self,
        hits: list[Any] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.hits = list(hits or [])
        self.error = error
        self.queries: list[tuple[str, set[str] | None]] = []

    def search(self, query: str, *, asset_types: set[str] | None = None) -> list[InstrumentCandidate]:
        self.queries.append((query, asset_types))
        if self.error is not None:
            raise self.error
        return list(self.hits)


def _candidate(
    *,
    instrument_id: str,
    display_name: str,
    source_symbol: str,
    asset_type: str = "equity",
    provider: str = "yahoo",
    currency: str = "USD",
    supported_for_history: bool = True,
) -> InstrumentCandidate:
    return InstrumentCandidate(
        instrument_id=instrument_id,
        display_name=display_name,
        provider=provider,
        source_symbol=source_symbol,
        asset_type=asset_type,
        currency=currency,
        supported_for_history=supported_for_history,
    )


def _ids(payload: list[dict[str, Any]]) -> list[str]:
    return [row["instrument_id"] for row in payload]


def _row(payload: list[dict[str, Any]], instrument_id: str) -> dict[str, Any]:
    matches = [row for row in payload if row["instrument_id"] == instrument_id]
    assert matches, f"{instrument_id} not in {_ids(payload)}"
    return matches[0]


@pytest.fixture
def fake_provider() -> FakeSearchProvider:
    return FakeSearchProvider()


@pytest.fixture
def client(fake_provider: FakeSearchProvider):
    app.dependency_overrides[get_search_provider] = lambda: fake_provider
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_search_provider, None)


def test_catalog_record_projects_to_instrument_candidate() -> None:
    record = next(r for r in WAVE_A_UNIVERSE if r.instrument_id == "equity:US:AAPL")
    assert isinstance(record, CatalogRecord)
    candidate = record.to_candidate()
    assert candidate.instrument_id == "equity:US:AAPL"
    assert candidate.display_name == "Apple Inc."
    assert candidate.provider == "yahoo"
    assert candidate.source_symbol == "AAPL"
    assert candidate.asset_type == "equity"
    assert candidate.currency == "USD"
    assert candidate.supported_for_history is True
    assert candidate.supported_for_snapshot is True
    assert candidate.supported_for_risk_factor is True
    assert record.risk_factor_mapping == "EquitySpot:AAPL"
    assert record.geography == "US"


def test_wave_a_universe_is_locked_and_omits_eurusd() -> None:
    ids = [r.instrument_id for r in WAVE_A_UNIVERSE]
    assert ids == [
        "equity:US:AAPL",
        "equity:US:MSFT",
        "equity:US:NVDA",
        "equity:US:SPY",
        "macro:FRED:DGS2",
        "macro:FRED:DGS5",
        "macro:FRED:DGS10",
    ]
    assert not any("EURUSD" in value for r in WAVE_A_UNIVERSE for value in (r.instrument_id, r.display_name))


def test_apple_search_api_returns_canonical_aapl(client: TestClient, fake_provider: FakeSearchProvider) -> None:
    fake_provider.hits = [
        _candidate(
            instrument_id="equity:US:AAPL",
            display_name="Apple Inc.",
            source_symbol="AAPL",
        )
    ]
    response = client.get("/api/v1/instruments/search", params={"q": "apple"})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    aapl = _row(body, "equity:US:AAPL")
    assert aapl["display_name"] == "Apple Inc."
    assert aapl["provider"] == "yahoo"
    assert aapl["source_symbol"] == "AAPL"
    assert aapl["asset_type"] == "equity"
    assert aapl["currency"] == "USD"
    assert aapl["supported_for_history"] is True
    assert aapl["supported_for_snapshot"] is True
    assert aapl["supported_for_risk_factor"] is True
    assert aapl["risk_factor_mapping"] == "EquitySpot:AAPL"
    assert aapl.get("coverage") is None


def test_apple_matches_curated_when_provider_is_down(client: TestClient, fake_provider: FakeSearchProvider) -> None:
    fake_provider.error = UnavailableError("provider unavailable")
    response = client.get("/api/v1/instruments/search", params={"q": "apple"})
    assert response.status_code == 200
    aapl = _row(response.json(), "equity:US:AAPL")
    assert aapl["supported_for_history"] is True
    assert aapl["risk_factor_mapping"] == "EquitySpot:AAPL"


def test_ambiguous_provider_hits_stay_distinct(client: TestClient, fake_provider: FakeSearchProvider) -> None:
    fake_provider.hits = [
        _candidate(instrument_id="equity:US:AAPL", display_name="Apple Inc.", source_symbol="AAPL"),
        _candidate(instrument_id="equity:US:TSLA", display_name="Tesla, Inc.", source_symbol="TSLA"),
    ]
    response = client.get("/api/v1/instruments/search", params={"q": "apple"})
    assert response.status_code == 200
    ids = _ids(response.json())
    assert ids.count("equity:US:AAPL") == 1
    assert "equity:US:TSLA" in ids
    assert "equity:US:AAPL" in ids


def test_unsupported_provider_hit_is_visible_with_capabilities_false(
    client: TestClient, fake_provider: FakeSearchProvider
) -> None:
    fake_provider.hits = [
        _candidate(
            instrument_id="equity:US:TSLA",
            display_name="Tesla, Inc.",
            source_symbol="TSLA",
            supported_for_history=True,
        )
    ]
    response = client.get("/api/v1/instruments/search", params={"q": "tesla"})
    assert response.status_code == 200
    tsla = _row(response.json(), "equity:US:TSLA")
    assert tsla["display_name"] == "Tesla, Inc."
    assert tsla["source_symbol"] == "TSLA"
    assert tsla["supported_for_history"] is False
    assert tsla["supported_for_snapshot"] is False
    assert tsla["supported_for_risk_factor"] is False
    assert tsla["risk_factor_mapping"] is None


def test_provider_cannot_overwrite_curated_identity(
    client: TestClient, fake_provider: FakeSearchProvider
) -> None:
    fake_provider.hits = [
        _candidate(
            instrument_id="equity:US:AAPL-WRONG",
            display_name="Apple from Yahoo",
            source_symbol="AAPL",
        )
    ]
    response = client.get("/api/v1/instruments/search", params={"q": "apple"})
    assert response.status_code == 200
    body = response.json()
    ids = _ids(body)
    assert "equity:US:AAPL-WRONG" not in ids
    assert ids.count("equity:US:AAPL") == 1
    aapl = _row(body, "equity:US:AAPL")
    assert aapl["display_name"] == "Apple Inc."
    assert aapl["supported_for_history"] is True
    assert aapl["supported_for_snapshot"] is True
    assert aapl["supported_for_risk_factor"] is True
    assert aapl["risk_factor_mapping"] == "EquitySpot:AAPL"
    assert aapl["source_symbol"] == "AAPL"


def test_symbol_mapping_round_trip_aapl(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/search", params={"q": "AAPL"})
    assert response.status_code == 200
    aapl = _row(response.json(), "equity:US:AAPL")
    assert aapl["source_symbol"] == "AAPL"
    assert aapl["provider"] == "yahoo"


def test_empty_and_whitespace_query_return_empty_list(client: TestClient, fake_provider: FakeSearchProvider) -> None:
    for raw in ("", "   ", "\t"):
        response = client.get("/api/v1/instruments/search", params={"q": raw})
        assert response.status_code == 200, raw
        assert response.json() == []
    assert fake_provider.queries == []


def test_malformed_provider_candidate_is_skipped_not_500(
    client: TestClient, fake_provider: FakeSearchProvider
) -> None:
    fake_provider.hits = [
        _candidate(instrument_id="equity:US:AAPL", display_name="Apple Inc.", source_symbol="AAPL"),
        {"not": "a candidate"},
    ]
    response = client.get("/api/v1/instruments/search", params={"q": "apple"})
    assert response.status_code == 200
    assert "equity:US:AAPL" in _ids(response.json())
    assert "traceback" not in response.text.lower()


def test_malformed_provider_error_without_curated_hits_is_mapped(
    client: TestClient, fake_provider: FakeSearchProvider
) -> None:
    fake_provider.error = MalformedResponseError("provider returned malformed JSON")
    response = client.get("/api/v1/instruments/search", params={"q": "zzzz-unknown"})
    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "malformed_response"
    assert "message" in body
    assert "details" in body
    assert "traceback" not in response.text.lower()


@pytest.mark.parametrize(
    ("exc", "status_code", "code"),
    [
        (UnavailableError("provider unavailable"), 503, "unavailable"),
        (RateLimitedError("provider rate limited"), 429, "rate_limited"),
        (AuthorizationError("provider authorization failed"), 401, "authorization"),
        (NotFoundError("provider resource not found"), 404, "not_found"),
    ],
)
def test_provider_errors_without_curated_hits_map_to_error_envelope(
    client: TestClient,
    fake_provider: FakeSearchProvider,
    exc: Exception,
    status_code: int,
    code: str,
) -> None:
    fake_provider.error = exc
    response = client.get("/api/v1/instruments/search", params={"q": "zzzz-unknown"})
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert "FRED_API_KEY" not in response.text


def test_fred_curated_hit_for_dgs10(client: TestClient, fake_provider: FakeSearchProvider) -> None:
    fake_provider.error = UnavailableError("yahoo down")
    response = client.get("/api/v1/instruments/search", params={"q": "dgs10"})
    assert response.status_code == 200
    dgs = _row(response.json(), "macro:FRED:DGS10")
    assert dgs["display_name"] == "US Treasury 10-Year"
    assert dgs["provider"] == "fred"
    assert dgs["source_symbol"] == "DGS10"
    assert dgs["asset_type"] == "macro"
    assert dgs["currency"] == "USD"
    assert dgs["supported_for_history"] is True
    assert dgs["supported_for_snapshot"] is True
    assert dgs["supported_for_risk_factor"] is True
    assert dgs["risk_factor_mapping"] == "RateZero:USD:10Y"
    assert fake_provider.queries == []


def test_fred_aliases_10y_and_treasury_10(client: TestClient) -> None:
    for query in ("10y", "treasury 10"):
        response = client.get("/api/v1/instruments/search", params={"q": query})
        assert response.status_code == 200, query
        assert "macro:FRED:DGS10" in _ids(response.json())


def test_canonical_id_appears_at_most_once(client: TestClient, fake_provider: FakeSearchProvider) -> None:
    fake_provider.hits = [
        _candidate(instrument_id="equity:US:AAPL", display_name="Apple Inc.", source_symbol="AAPL"),
        _candidate(instrument_id="equity:US:AAPL-WRONG", display_name="Apple Inc.", source_symbol="AAPL"),
    ]
    response = client.get("/api/v1/instruments/search", params={"q": "apple"})
    ids = _ids(response.json())
    assert len(ids) == len(set(ids))
    assert ids.count("equity:US:AAPL") == 1


def test_search_dual_mounted_on_legacy_and_v1(client: TestClient) -> None:
    legacy = client.get("/instruments/search", params={"q": "msft"})
    versioned = client.get("/api/v1/instruments/search", params={"q": "msft"})
    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert "equity:US:MSFT" in _ids(legacy.json())
    assert "equity:US:MSFT" in _ids(versioned.json())


def test_search_response_never_includes_fred_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "super-secret-fred-key")
    response = client.get("/api/v1/instruments/search", params={"q": "dgs10"})
    assert response.status_code == 200
    assert "super-secret-fred-key" not in response.text
    assert "FRED_API_KEY" not in response.text
    assert os.environ["FRED_API_KEY"] == "super-secret-fred-key"


def test_search_catalog_skips_invalid_candidate_objects() -> None:
    provider = FakeSearchProvider(
        [
            _candidate(instrument_id="equity:US:TSLA", display_name="Tesla, Inc.", source_symbol="TSLA"),
            object(),
        ]
    )
    result = search_catalog("tesla", provider=provider)
    assert [hit.instrument_id for hit in result.hits] == ["equity:US:TSLA"]
    assert all(hit.supported_for_history is False for hit in result.hits)


def test_catalog_service_does_not_import_fastapi() -> None:
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "market" / "catalog"
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert "fastapi" not in imported, py
        for name in imported:
            assert not str(name).startswith("app.risk")
            assert not str(name).startswith("app.pricing")


def test_instrument_candidate_still_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        InstrumentCandidate(
            instrument_id="equity:US:AAPL",
            display_name="Apple Inc.",
            provider="yahoo",
            source_symbol="AAPL",
            asset_type="equity",
            currency="USD",
            extra_field="nope",  # type: ignore[call-arg]
        )
