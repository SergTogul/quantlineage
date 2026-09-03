# ADR 008: Canonical `/api/v1` prefix and legacy dual-mount sunset

- Status: Accepted - Date: 2026-09-02
- Owners: Backend/API Engineer; Lead Architect

## Context

 dual-mounted every public domain router at unversioned paths and under
``/api/v1``. Clients (including the React SPA) still call legacy paths. We need
a single canonical prefix without breaking existing callers in this workstream.

## Decision

1. **Canonical prefix** is ``/api/v1``. New clients and docs use only that prefix.
2. **Keep dual-mount** until a published sunset window and explicit removal
 approval (non-breaking for ).
3. **Deprecate legacy** with HTTP headers on unversioned dual-mounted responses
 only: ``Deprecation: true``, ``Sunset`` (HTTP-date), and
 ``Link: </api/v1{path}>; rel="successor-version"``.
4. **Do not remove** legacy paths in . Planned earliest removal window:
 **2027-03-02**, gated on Frontend migration + Lead Architect sign-off
 (see ``docs/api/v1_canonical_and_legacy_sunset.md``).
5. **SPA migration** to ``/api/v1`` is a Frontend (Agent 08) follow-up (**DONE**
 2026-09-02). Legacy dual-mount remains until the removal gate.

## Alternatives considered

| Alternative | Why rejected / deferred |
|-------------|-------------------------|
| Remove legacy immediately | Breaks SPA and any external callers; violates non-breaking preference. |
| Version only risk-runs | Superseded by full dual-mount; incomplete as a long-term story. |
| Skip deprecation headers | Harder for clients to discover the successor; headers are low-risk. |
| Force SPA migrate in same PR | Optional per ROADMAP; higher blast radius for close-out; hand off to . |

## Consequences

- OpenAPI continues to list both mounts until removal.
- Error model and typed responses remain shared across mounts .
- A future breaking change will delete the unversioned ``include_router`` mounts
 and the deprecation middleware.
