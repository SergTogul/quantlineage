# ADR 008: Canonical `/api/v1` prefix and legacy dual-mount sunset

- Status: Accepted (M7.6)
- Date: 2026-09-02
- Owners: Backend/API Engineer; Lead Architect

## Context

M7.2 dual-mounted every public domain router at unversioned paths and under
``/api/v1``. Clients (including the React SPA) still call legacy paths. We need
a single canonical prefix without breaking existing callers in this milestone.

## Decision

1. **Canonical prefix** is ``/api/v1``. New clients and docs use only that prefix.
2. **Keep dual-mount** until a published sunset window and explicit removal
   approval (non-breaking for M7.6).
3. **Deprecate legacy** with HTTP headers on unversioned dual-mounted responses
   only: ``Deprecation: true``, ``Sunset`` (HTTP-date), and
   ``Link: </api/v1{path}>; rel="successor-version"``.
4. **Do not remove** legacy paths in M7.6. Planned earliest removal window:
   **2027-03-02**, gated on Frontend migration + Lead Architect sign-off
   (see ``docs/api/v1_canonical_and_legacy_sunset.md``).
5. **SPA migration** to ``/api/v1`` is a Frontend (Agent 08) follow-up; leaving
   the UI on legacy for M7.6 is acceptable and documented.

## Alternatives considered

| Alternative | Why rejected / deferred |
|-------------|-------------------------|
| Remove legacy immediately | Breaks SPA and any external callers; violates M7.6 non-breaking preference. |
| Version only risk-runs | Superseded by M7.2 full dual-mount; incomplete as a long-term story. |
| Skip deprecation headers | Harder for clients to discover the successor; headers are low-risk. |
| Force SPA migrate in same PR | Optional per ROADMAP; higher blast radius for M7 close-out; hand off to M8. |

## Consequences

- OpenAPI continues to list both mounts until removal.
- Error model and typed responses remain shared across mounts (M7.3–M7.5).
- A future breaking change will delete the unversioned ``include_router`` mounts
  and the deprecation middleware.
