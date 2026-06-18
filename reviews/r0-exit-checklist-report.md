# R0 Final Exit Checklist Report

Date: 2026-09-09  
Branch: `r0-core-remediation`  
Owner: Lead Architect / documentation honesty

## Verdict

**Milestone R0 COMPLETE.** All P0 and P1 root findings are CLOSED. RF-020 is CLOSED. P2 RF-017 / RF-018 / RF-019 are **ACCEPTED / DEFERRED** (not CLOSED as MET). Named accepted residuals stay `[~]` / **not MET**.

## Checklist scoring

`[x]` = MET. `[~]` = accepted residual, not MET.

### Correctness — MET

Exact VaR/ES goldens (RF-003), approximate P&L unit goldens (RF-004), full-reval one-trade goldens, snapshot-authoritative market (RF-001), per-factor historical moves (RF-005), scenario contribution reconcile (RF-006).

### QuantLib — MET

Snapshot as-of drives evaluation date; process-owned QuantLib state; contamination test; QuantLib mandatory in PR-FULL (RF-002, RF-016 hard-gate).

### Execution — MET

One-pass scenario apply (RF-006); full-reval benchmark recorded (RF-007, N×S PARTIAL but recorded); hierarchy reuses trade-level results (RF-008); heavy work on RiskRun / Compose worker (RF-007 / RF-015); dashboard does not launch redundant full calculations (RF-015).

### Persistence / runs — MET

RiskRun input identity (RF-009 / RF-013); API and worker same dataset (RF-009); client cannot overwrite `global-macro` by ID (RF-013); Postgres worker lifecycle tests (RF-009).

### Security / operability — MET except RF-014 shared auth

Local Compose loopback, Postgres not publicly mapped by default, finite numbers, workload caps, sanitized errors: **MET**.

- [~] shared deployment requires auth/authorization — **accepted residual (not MET):** RF-014 object ACLs / TLS / secret management. Shared-token gate is authentication only, not authorization.

### QA / CI — MET except labeled-runner SLA and QA-024

PR-FAST / PR-FULL QuantLib hard-gate / native / frontend / E2E / static analysis / NIGHTLY Postgres two-worker / larger full-reval / QuantLib E2E: **MET**. Backend suite claim is the recorded Phase A baseline (dated, **not a live** re-run).

- [~] labeled-runner SLA-K1/K2 — **accepted residual (not MET):** RF-016; no labeled runner; SLA-K1/K2 not CI-enforced; do not run `check_m6_sla.py` on `ubuntu-latest`.
- [~] QA-024 demo-artifact range check — leftover residual, **not MET**.

### Documentation — MET with dated-count disclaimer

FINDINGS statuses updated; ROADMAP includes Milestone R0 **COMPLETE**; `docs/known_limitations.md` names the residuals; benchmark/test claims keep the Phase A **not re-run** disclaimer (allowed; not a stale-as-live lie).

## P2

| ID | Status | Why not CLOSED as MET |
|---|---|---|
| RF-017 | ACCEPTED / DEFERRED | Do not expand C++ VaR/QuantLib. ABI slice landed; default kernel remains python/NumPy. |
| RF-018 | ACCEPTED / DEFERRED | Do not TypeScript-rewrite in R0. |
| RF-019 | ACCEPTED / DEFERRED | AI after deterministic APIs. |
| RF-020 | CLOSED | Docs match reality: R0 COMPLETE with named residuals; dated counts disclaimed. |

## Why COMPLETE (not KEEP OPEN)

Every P0 and P1 is CLOSED. The exit checklist distinguishes MET vs accepted residual. ROADMAP Current gate says COMPLETE and does not remain IN PROGRESS. RF-020 CLOSE is honest because known_limitations matches FINDINGS and suite counts are not presented as a live matrix.

KEEP OPEN would be required if any P1 were still IN PROGRESS, if `[~]` residuals were checked `[x]`, or if ROADMAP said IN PROGRESS while claiming COMPLETE.
