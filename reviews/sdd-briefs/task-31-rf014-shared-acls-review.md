# Task 31 Review — RF-014 shared ACLs + TLS + secrets

**Reviewer:** independent (read-only of `b592be9..1aacdab`, then Important follow-up)
**Range reviewed:** `b592be9` → `1aacdab`
**Verdict on the three shared cells:** **APPROVE CLOSE** (no IDOR bypass, 443 not 8000, no hardcoded shared DB password)
**Important follow-ups:** token first-match, NULL-owner 403 pin, shared SPA same-origin — implemented after this review (uncommitted until tests pass)

Full hunt notes: overlapping `RISKFORGE_API_TOKEN` last-wins could remap a `TOKENS` principal; GET list is demo catalog only; attach-stored is 403; live calculate POSTs take a client body (not stored IDOR); `owner=None` fail-closed in code.

Do not restore Milestone R0 COMPLETE while labeled-runner SLA is not MET.
