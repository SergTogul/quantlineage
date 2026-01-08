# Canonical API prefix `/api/v1` and legacy path sunset (M7.6)

**Owner:** Backend/API Engineer (with Lead Architect)  
**Status:** Dual-mount active; legacy paths deprecated but still served  
**Date:** 2026-09-02

## Canonical prefix

All new clients and documentation **must** use:

```text
/api/v1/...
```

Examples (same handlers as the legacy dual-mount):

```text
GET  /api/v1/health
GET  /api/v1/portfolio
POST /api/v1/market/snapshot
POST /api/v1/risk/summary
POST /api/v1/risk/var
POST /api/v1/risk/stress
POST /api/v1/risk/runs
GET  /api/v1/risk/runs/{run_id}
```

OpenAPI / Swagger (`/docs`, `/openapi.json`) lists both mounts. Prefer the
`/api/v1` paths when copying examples.

## What stays dual-mounted now

Until removal (below), every public domain router is mounted **twice**:

| Mount | Prefix | Status |
|-------|--------|--------|
| Canonical | `/api/v1` | Supported; no deprecation headers |
| Legacy | unversioned (`/health`, `/portfolio`, `/market/*`, `/risk/*`) | Deprecated; still fully functional |

`risk_runs` is unified as `/risk/runs` and `/api/v1/risk/runs` only (no nested
`/api/v1/api/v1/...`). Non-API surfaces (`/docs`, `/redoc`, `/openapi.json`) are
not dual-mounted and are not deprecated.

## Deprecation response headers (legacy only)

Legacy responses include:

| Header | Value | Meaning |
|--------|-------|---------|
| `Deprecation` | `true` | Path is deprecated |
| `Sunset` | `Tue, 02 Mar 2027 00:00:00 GMT` | Planned earliest removal window |
| `Link` | `</api/v1{path}>; rel="successor-version"` | Canonical successor URL |

`/api/v1/...` responses do **not** carry these headers. Bodies, status codes,
and error envelopes (`{code, message, details}`) are unchanged on both mounts.

## Sunset timeline

| Phase | When | Action |
|-------|------|--------|
| **Deprecate** (this task) | 2026-09-02 (M7.6) | Document `/api/v1` as canonical; dual-mount kept; Deprecation/Sunset/Link on legacy |
| **Migrate clients** | **DONE** 2026-09-02 (M8 Frontend) | SPA `frontend/src/api.js` uses `/api/v1`; legacy dual-mount kept for other callers |
| **Remove legacy** | On/after **2027-03-02**, only with Lead Architect approval | Drop unversioned dual-mount; require `/api/v1` |

Removal is **not** automatic on the Sunset date. Gates before unmounting legacy:

1. Frontend Risk UX (Agent 08) migrated `api.js` to `/api/v1` (**DONE** 2026-09-02). E2E / scripts / Compose smoke may still use legacy until updated.
2. No remaining in-repo callers on unversioned paths (scripts, Compose smoke, docs examples updated).
3. Lead Architect signs off on a breaking-change note in ROADMAP / release notes.

## How UI / clients should migrate

1. Prefix every API path with `/api/v1` (e.g. `/portfolio` → `/api/v1/portfolio`).
2. Keep using the same JSON request/response shapes — M7.2–M7.5 did not fork schemas by mount.
3. Optionally assert that canonical responses lack `Deprecation` / `Sunset`.
4. After migration, ignore legacy paths; they will be removed in a later milestone.

**Frontend note:** SPA `api.js` migrated to `/api/v1` (2026-09-02, M8). Legacy
unversioned dual-mount remains until the removal gate above.

## Related

- ADR: `docs/adr/008-api-v1-canonical-and-legacy-sunset.md`
- Dual-mount wiring: `backend/app/main.py`
- Header middleware: `backend/app/api/legacy_deprecation.py`
- Compatibility tests: `backend/tests/test_api_v1_compatibility.py`,
  `backend/tests/test_api_legacy_deprecation.py`
