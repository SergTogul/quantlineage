"""M7.6: Deprecation / Sunset / Link headers on legacy paths only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.legacy_deprecation import (
    LEGACY_DEPRECATION_VALUE,
    LEGACY_SUNSET_HTTP_DATE,
    is_legacy_api_path,
    successor_version_path,
)


def test_m76_is_legacy_api_path_helpers() -> None:
    assert is_legacy_api_path("/health")
    assert is_legacy_api_path("/portfolio")
    assert is_legacy_api_path("/portfolios")
    assert is_legacy_api_path("/portfolios/equity-vol")
    assert is_legacy_api_path("/market/snapshot")
    assert is_legacy_api_path("/risk/summary")
    assert is_legacy_api_path("/risk/runs/abc")
    assert not is_legacy_api_path("/api/v1/health")
    assert not is_legacy_api_path("/api/v1/risk/summary")
    assert not is_legacy_api_path("/docs")
    assert not is_legacy_api_path("/openapi.json")
    assert successor_version_path("/risk/var") == "/api/v1/risk/var"


@pytest.mark.parametrize(
    "legacy_path,v1_path",
    [
        ("/health", "/api/v1/health"),
        ("/portfolio", "/api/v1/portfolio"),
        ("/portfolios", "/api/v1/portfolios"),
        ("/risk/stress/scenarios", "/api/v1/risk/stress/scenarios"),
    ],
)
def test_m76_legacy_get_has_deprecation_headers(
    legacy_path: str, v1_path: str
) -> None:
    from app.main import app

    with TestClient(app) as client:
        legacy = client.get(legacy_path)
        versioned = client.get(v1_path)
        assert legacy.status_code == 200
        assert versioned.status_code == 200

        assert legacy.headers.get("Deprecation") == LEGACY_DEPRECATION_VALUE
        assert legacy.headers.get("Sunset") == LEGACY_SUNSET_HTTP_DATE
        assert (
            legacy.headers.get("Link")
            == f'<{v1_path}>; rel="successor-version"'
        )

        assert "Deprecation" not in versioned.headers
        assert "Sunset" not in versioned.headers
        assert "successor-version" not in (versioned.headers.get("Link") or "")


def test_m76_legacy_post_has_deprecation_headers() -> None:
    from app.main import app

    with TestClient(app) as client:
        portfolio = client.get("/api/v1/portfolio").json()
        legacy = client.post("/risk/summary", json=portfolio)
        versioned = client.post("/api/v1/risk/summary", json=portfolio)
        assert legacy.status_code == 200
        assert versioned.status_code == 200
        assert legacy.json() == versioned.json()

        assert legacy.headers.get("Deprecation") == LEGACY_DEPRECATION_VALUE
        assert legacy.headers.get("Sunset") == LEGACY_SUNSET_HTTP_DATE
        assert (
            legacy.headers.get("Link")
            == '</api/v1/risk/summary>; rel="successor-version"'
        )
        assert "Deprecation" not in versioned.headers


def test_m76_docs_not_deprecated() -> None:
    from app.main import app

    with TestClient(app) as client:
        docs = client.get("/openapi.json")
        assert docs.status_code == 200
        assert "Deprecation" not in docs.headers
        assert "Sunset" not in docs.headers
