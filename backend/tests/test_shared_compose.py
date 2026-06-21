"""RF-014: shared Compose TLS terminator + secret model (file pins).

Local ``docker-compose.yml`` stays unauthenticated loopback HTTP.
Shared overlay/file publishes 443 (not raw 8000) and does not hardcode
``POSTGRES_PASSWORD=riskforge``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.yml"
SHARED_COMPOSE = REPO_ROOT / "docker-compose.shared.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.shared.example"


def test_shared_compose_file_exists() -> None:
    assert SHARED_COMPOSE.is_file(), "docker-compose.shared.yml must exist"


def test_shared_compose_publishes_443_not_raw_8000() -> None:
    text = SHARED_COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"443:443", text), "shared profile must publish 443"
    # Host publish of the API port is forbidden; expose/internal 8000 is OK.
    assert not re.search(r"""['"][^'"\n]*8000:8000""", text)
    assert "0.0.0.0:8000" not in text
    assert "127.0.0.1:8000:8000" not in text


def test_shared_compose_does_not_hardcode_demo_postgres_password() -> None:
    text = SHARED_COMPOSE.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD=riskforge" not in text
    assert "POSTGRES_PASSWORD: riskforge" not in text
    assert "riskforge:riskforge@" not in text
    assert "${POSTGRES_PASSWORD:?}" in text


def test_shared_env_example_documents_secret_placeholders() -> None:
    assert ENV_EXAMPLE.is_file()
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD=" in text
    assert "RISKFORGE_API_TOKEN=" in text
    assert "riskforge" not in text.lower() or "POSTGRES_PASSWORD=" in text
    assert not re.search(r"^POSTGRES_PASSWORD=riskforge\s*$", text, re.MULTILINE)


def test_local_compose_keeps_demo_password_and_loopback_8000() -> None:
    text = LOCAL_COMPOSE.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD: riskforge" in text
    assert "127.0.0.1:8000:8000" in text
    assert "RISKFORGE_SHARED_DEPLOYMENT:" not in text


def test_shared_frontend_bakes_same_origin_api() -> None:
    text = SHARED_COMPOSE.read_text(encoding="utf-8")
    assert "VITE_API_BASE_URL: same-origin" in text
    dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG VITE_API_BASE_URL" in dockerfile
