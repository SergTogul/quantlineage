"""Default Compose publishes must bind to loopback (R0.11.1 / RF-014 / SEC-004).

Scans every ``ports:`` entry on every service. PyYAML is not a backend
dependency, so this file does not call ``yaml.safe_load``. Does not require
Docker to be running.
"""

from __future__ import annotations

import re
from pathlib import Path

COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"

# Host:container mappings that must be published, each prefixed with 127.0.0.1.
REQUIRED_PUBLISHES = {
    "postgres": "5432:5432",
    "backend": "8000:8000",
    "frontend": "5173:80",
}

LOOPBACK_SNIPPET = """
services:
  postgres:
    image: postgres:16-alpine
    ports: ["127.0.0.1:5432:5432"]
  backend:
    build: ./backend
    ports: ["127.0.0.1:8000:8000"]
  worker:
    build: ./backend
    command: ["python", "-m", "app.worker"]
  frontend:
    build: ./frontend
    ports: ["127.0.0.1:5173:80"]
"""


_SERVICE_KEY = re.compile(r"^  ([A-Za-z0-9._-]+):\s*(?:#.*)?$")
_TOP_KEY = re.compile(r"^[A-Za-z0-9._-]+:")
_PORTS_INLINE_LIST = re.compile(r"^    ports:\s*\[(.*)\]\s*(?:#.*)?$")
_PORTS_BLOCK = re.compile(r"^    ports:\s*(?:#.*)?$")
_PORTS_SCALAR = re.compile(r"^    ports:\s+(\S.*)$")
_PROTO_SUFFIX = re.compile(r"/(tcp|udp)$", re.IGNORECASE)
_CONTAINER_ONLY = re.compile(r"^\d+(?:-\d+)?$")


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _split_top_commas(inner: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    depth = 0
    for char in inner:
        if quote:
            buf.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            buf.append(char)
            continue
        if char == "{":
            depth += 1
            buf.append(char)
            continue
        if char == "}":
            depth -= 1
            buf.append(char)
            continue
        if char == "," and depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(char)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_flow_mapping(raw: str) -> dict[str, str] | None:
    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    inner = text[1:-1].strip()
    parsed: dict[str, str] = {}
    if not inner:
        return parsed
    for part in _split_top_commas(inner):
        if ":" not in part:
            return None
        key, _, value = part.partition(":")
        parsed[key.strip()] = _unquote(value)
    return parsed


def _flow_item(item: str) -> object:
    stripped = item.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        parsed = _parse_flow_mapping(stripped)
        return parsed if parsed is not None else stripped
    return _unquote(stripped)


def _parse_flow_list(inner: str) -> list[object]:
    return [_flow_item(part) for part in _split_top_commas(inner)]


def _iter_service_bodies(compose_text: str) -> dict[str, list[str]] | None:
    if not re.search(r"^services:\s*(?:#.*)?$", compose_text, re.MULTILINE):
        return None
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    in_services = False
    for line in compose_text.splitlines():
        if not in_services:
            if re.match(r"^services:\s*(?:#.*)?$", line):
                in_services = True
            continue
        if _TOP_KEY.match(line) and not line.startswith((" ", "\t")):
            break
        service = _SERVICE_KEY.match(line)
        if service:
            current = service.group(1)
            bodies[current] = []
            continue
        if current is not None:
            bodies[current].append(line)
    return bodies


def _looks_like_short_port(item: str) -> bool:
    text = _unquote(item)
    return text.startswith("[") or bool(re.match(r"^\d", text))


def _parse_block_port_items(lines: list[str]) -> list[object] | None:
    entries: list[object] = []
    current_map: dict[str, str] | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= 4:
            break
        if stripped.startswith("-"):
            if current_map is not None:
                entries.append(current_map)
                current_map = None
            rest = stripped[1:].strip()
            if not rest:
                current_map = {}
                continue
            if rest.startswith("{") and rest.endswith("}"):
                parsed = _parse_flow_mapping(rest)
                if parsed is None:
                    return None
                entries.append(parsed)
                continue
            key, sep, value = rest.partition(":")
            if sep and not _looks_like_short_port(rest):
                current_map = {key.strip(): _unquote(value)}
                continue
            entries.append(_unquote(rest))
            continue
        if current_map is not None and ":" in stripped:
            key, _, value = stripped.partition(":")
            current_map[key.strip()] = _unquote(value)
            continue
        return None
    if current_map is not None:
        entries.append(current_map)
    return entries


def _port_entries_from_body(body_lines: list[str]) -> list[object] | None:
    entries: list[object] = []
    index = 0
    while index < len(body_lines):
        line = body_lines[index]
        index += 1
        if line.strip().startswith("#"):
            continue
        inline = _PORTS_INLINE_LIST.match(line)
        if inline:
            entries.extend(_parse_flow_list(inline.group(1)))
            continue
        if _PORTS_BLOCK.match(line):
            block = _parse_block_port_items(body_lines[index:])
            if block is None:
                return None
            entries.extend(block)
            continue
        scalar = _PORTS_SCALAR.match(line)
        if scalar:
            value = scalar.group(1).split("#", 1)[0].strip()
            if value.startswith("["):
                return None
            entries.append(_unquote(value))
    return entries


def _parse_port_entry(raw: object) -> tuple[bool, str | None, str | None, str | None]:
    """Return (parsed, host_ip, published, target)."""
    if isinstance(raw, dict):
        if "target" not in raw:
            return False, None, None, None
        host_ip = raw.get("host_ip")
        published = raw.get("published")
        target = raw.get("target")
        host_ip_s = None if host_ip in (None, "") else str(host_ip)
        published_s = None if published in (None, "") else str(published)
        return True, host_ip_s, published_s, str(target)

    if not isinstance(raw, str):
        return False, None, None, None
    text = raw.strip()
    if not text:
        return False, None, None, None
    text = _PROTO_SUFFIX.sub("", text)

    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            return False, None, None, None
        host_ip = text[1:end]
        rest = text[end + 1 :]
        if not rest.startswith(":"):
            return False, None, None, None
        parts = rest[1:].split(":")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return False, None, None, None
        return True, host_ip, parts[0], parts[1]

    parts = text.split(":")
    if not parts or any(part == "" for part in parts):
        return False, None, None, None
    if len(parts) == 1:
        if not _CONTAINER_ONLY.fullmatch(parts[0]):
            return False, None, None, None
        return True, None, None, parts[0]
    if len(parts) == 2:
        return True, None, parts[0], parts[1]
    if len(parts) == 3:
        return True, parts[0], parts[1], parts[2]
    return False, None, None, None


def published_port_violations(compose_text: str) -> list[str]:
    """Every published port on every service must bind 127.0.0.1; unparsed entries fail closed."""
    services = _iter_service_bodies(compose_text)
    if services is None or not services:
        return ["failed to parse Compose services"]

    violations: list[str] = []
    found_required = {name: False for name in REQUIRED_PUBLISHES}

    for service, body_lines in services.items():
        entries = _port_entries_from_body(body_lines)
        if entries is None:
            violations.append(f"{service}: unparsed ports key")
            continue
        for raw in entries:
            parsed, host_ip, published, target = _parse_port_entry(raw)
            if not parsed:
                violations.append(f"{service}: unparsed port entry {raw!r}")
                continue
            if host_ip != "127.0.0.1":
                violations.append(
                    f"{service}: published port {raw!r} is not bound to 127.0.0.1"
                )
                continue
            if (
                service in REQUIRED_PUBLISHES
                and published is not None
                and target is not None
                and f"{published}:{target}" == REQUIRED_PUBLISHES[service]
            ):
                found_required[service] = True

    for service, mapping in REQUIRED_PUBLISHES.items():
        if not found_required[service]:
            violations.append(f"{service}: missing 127.0.0.1:{mapping}")
    return violations


def test_compose_published_ports_bind_loopback():
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert published_port_violations(compose_text) == []


def test_second_unbound_postgres_mapping_fails():
    text = LOOPBACK_SNIPPET.replace(
        'ports: ["127.0.0.1:5432:5432"]',
        'ports: ["127.0.0.1:5432:5432", "15432:5432"]',
    )
    assert published_port_violations(text), (
        "postgres dual-publish 127.0.0.1:5432:5432 plus 15432:5432 must fail"
    )


def test_publishing_worker_unbound_fails():
    text = LOOPBACK_SNIPPET.replace(
        '    command: ["python", "-m", "app.worker"]',
        '    ports: ["8001:8001"]\n    command: ["python", "-m", "app.worker"]',
    )
    assert published_port_violations(text), "worker ports: [\"8001:8001\"] must fail"


def test_extra_service_unbound_publish_fails():
    text = LOOPBACK_SNIPPET + "  debug:\n    ports: [\"5432:5433\"]\n"
    assert published_port_violations(text), "extra service ports: [\"5432:5433\"] must fail"


def test_unbound_short_form_without_host_ip_fails():
    text = LOOPBACK_SNIPPET.replace(
        'ports: ["127.0.0.1:5432:5432"]',
        'ports: ["5432:5432"]',
    )
    assert published_port_violations(text)


def test_all_interfaces_host_ip_fails():
    text = LOOPBACK_SNIPPET.replace(
        'ports: ["127.0.0.1:5432:5432"]',
        'ports: ["0.0.0.0:5432:5432"]',
    )
    assert published_port_violations(text)


def test_wrong_host_port_does_not_satisfy_required_mapping():
    text = LOOPBACK_SNIPPET.replace(
        'ports: ["127.0.0.1:5432:5432"]',
        'ports: ["127.0.0.1:15432:5432"]',
    )
    assert published_port_violations(text), (
        "127.0.0.1:15432:5432 must not satisfy required postgres 5432:5432"
    )


def test_tcp_suffix_is_accepted_as_loopback():
    text = LOOPBACK_SNIPPET.replace(
        'ports: ["127.0.0.1:5432:5432"]',
        'ports: ["127.0.0.1:5432:5432/tcp"]',
    )
    assert published_port_violations(text) == []


def test_long_form_host_ip_is_accepted():
    text = LOOPBACK_SNIPPET.replace(
        '    ports: ["127.0.0.1:5432:5432"]\n',
        "    ports:\n"
        "      - target: 5432\n"
        "        published: 5432\n"
        "        host_ip: 127.0.0.1\n",
    )
    assert published_port_violations(text) == []


def test_unparsed_port_entry_fails_closed():
    text = LOOPBACK_SNIPPET.replace(
        'ports: ["127.0.0.1:5432:5432"]',
        'ports: ["127.0.0.1:5432:5432", "not-a-valid-port-mapping"]',
    )
    assert published_port_violations(text), "unparsed ports entries must fail closed"
