"""Container/dependency hardening (R0.11.6 / RF-014 / RF-018).

Static checks on Dockerfiles and frontend package.json. Does not require Docker.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
FRONTEND_NGINX_CONF = REPO_ROOT / "frontend" / "nginx.conf"
FRONTEND_DOCKERIGNORE = REPO_ROOT / "frontend" / ".dockerignore"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"

_NGINX_TEMP_DIRECTIVES = (
    "client_body_temp_path",
    "proxy_temp_path",
    "fastcgi_temp_path",
    "uwsgi_temp_path",
    "scgi_temp_path",
)


def _dockerfile_logical_lines(text: str) -> list[str]:
    """Join continuation lines; drop blank and full-line comments."""
    logical: list[str] = []
    buf = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not buf and (not stripped or stripped.startswith("#")):
            continue
        piece = raw.rstrip()
        if buf:
            buf = f"{buf} {piece.lstrip()}"
        else:
            buf = piece
        if buf.endswith("\\"):
            buf = buf[:-1].rstrip()
            continue
        logical.append(buf)
        buf = ""
    if buf:
        logical.append(buf)
    return logical


def _instruction_args(text: str, keyword: str) -> list[str]:
    found: list[str] = []
    pattern = re.compile(rf"(?i)^{re.escape(keyword)}\s+")
    for line in _dockerfile_logical_lines(text):
        stripped = line.strip()
        if pattern.match(stripped):
            found.append(stripped.split(None, 1)[1].strip())
    return found


def _final_stage(text: str) -> str:
    lines = _dockerfile_logical_lines(text)
    last_from = 0
    for i, line in enumerate(lines):
        if re.match(r"(?i)^FROM\s+", line.strip()):
            last_from = i
    return "\n".join(lines[last_from:])


def _user_identity(user_arg: str) -> str:
    return user_arg.split(":", 1)[0].strip()


def _final_stage_users(text: str) -> list[str]:
    return _instruction_args(_final_stage(text), "USER")


def _run_invokes_npm(run_arg: str, npm_cmd: str) -> bool:
    return re.search(rf"(?:^|[;&|]\s*)npm\s+{re.escape(npm_cmd)}\b", run_arg) is not None


def _nginx_code_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if "#" in raw:
            raw = raw[: raw.index("#")]
        stripped = raw.strip().rstrip(";")
        if stripped:
            lines.append(stripped)
    return lines


def _nginx_directives(text: str) -> list[tuple[str, str]]:
    directives: list[tuple[str, str]] = []
    for line in _nginx_code_lines(text):
        line = line.rstrip("{").strip()
        if not line or line == "}":
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            directives.append((parts[0], parts[1]))
    return directives


def _path_is_writable_runtime(path: str) -> bool:
    return path == "/tmp" or path.startswith("/tmp/")


def _dockerignore_entries(text: str) -> set[str]:
    entries: set[str] = set()
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.add(stripped.rstrip("/"))
    return entries


def test_frontend_package_json_dependencies_are_not_latest():
    package = json.loads(FRONTEND_PACKAGE_JSON.read_text(encoding="utf-8"))
    latest: list[str] = []
    for section in ("dependencies", "devDependencies"):
        deps = package.get(section) or {}
        for name, version in deps.items():
            if str(version).strip() == "latest":
                latest.append(f"{section}:{name}")
    assert not latest, f"frontend/package.json must not use 'latest': {latest}"


def test_frontend_dockerfile_uses_npm_ci():
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    runs = _instruction_args(text, "RUN")
    assert any(_run_invokes_npm(run, "ci") for run in runs), (
        "frontend Dockerfile must have a RUN whose install command is npm ci"
    )
    install_runs = [run for run in runs if _run_invokes_npm(run, "install")]
    assert not install_runs, f"frontend Dockerfile must not RUN npm install: {install_runs}"


def test_comment_npm_ci_does_not_satisfy_install_requirement():
    text = "# RUN npm ci\nRUN npm install\n"
    runs = _instruction_args(text, "RUN")
    assert not any(_run_invokes_npm(run, "ci") for run in runs)
    assert any(_run_invokes_npm(run, "install") for run in runs)


def test_frontend_final_stage_drops_to_non_root_user():
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    users = _final_stage_users(text)
    assert users, "frontend Dockerfile final stage must contain a USER instruction"
    final = _user_identity(users[-1])
    assert final not in {"root", "0"}, f"final-stage USER must be non-root, got {users[-1]!r}"


def test_comment_or_build_stage_user_is_not_final_user():
    comment_only = "FROM nginx:alpine\n# USER nginx\nCMD nginx\n"
    assert _final_stage_users(comment_only) == []

    build_stage_only = (
        "FROM node:22-alpine AS build\n"
        "USER nginx\n"
        "FROM nginx:alpine\n"
        "CMD nginx\n"
    )
    assert _final_stage_users(build_stage_only) == []


def test_frontend_nginx_conf_is_non_root_safe():
    text = FRONTEND_NGINX_CONF.read_text(encoding="utf-8")
    directives = _nginx_directives(text)
    names = [name for name, _ in directives]
    assert "user" not in names, "nginx.conf must not contain a user directive"
    pids = [value for name, value in directives if name == "pid"]
    assert pids, "nginx.conf must set pid under a writable location"
    assert all(_path_is_writable_runtime(value.split()[0]) for value in pids), (
        f"nginx pid must be under /tmp, got {pids!r}"
    )
    present = {name: value for name, value in directives if name in _NGINX_TEMP_DIRECTIVES}
    missing = [name for name in _NGINX_TEMP_DIRECTIVES if name not in present]
    assert not missing, f"nginx.conf missing temp paths: {missing}"
    bad = {
        name: value
        for name, value in present.items()
        if not _path_is_writable_runtime(value.split()[0])
    }
    assert not bad, f"nginx temp paths must be under /tmp, got {bad!r}"


def test_comment_user_directive_is_ignored_in_nginx_conf():
    text = "# user nginx;\npid /tmp/nginx.pid;\n"
    names = [name for name, _ in _nginx_directives(text)]
    assert "user" not in names
    assert "pid" in names


def test_frontend_dockerignore_excludes_host_build_artifacts():
    assert FRONTEND_DOCKERIGNORE.is_file(), "frontend/.dockerignore must exist"
    entries = _dockerignore_entries(FRONTEND_DOCKERIGNORE.read_text(encoding="utf-8"))
    missing = [name for name in ("node_modules", "dist") if name not in entries]
    assert not missing, f"frontend/.dockerignore must list {missing}"


def test_backend_dockerfile_drops_to_non_root_user():
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    users: list[str] = []
    for line in _dockerfile_logical_lines(text):
        stripped = line.strip()
        if re.match(r"(?i)^USER\s+", stripped):
            users.append(stripped.split(None, 1)[1].strip())
    assert users, "backend Dockerfile must contain a USER instruction"
    final = _user_identity(users[-1])
    assert final not in {"root", "0"}, f"final USER must be non-root, got {users[-1]!r}"
