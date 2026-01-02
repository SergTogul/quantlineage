# Verification

Final verification in the execution sandbox:

- Backend pytest: **32 passed, 1 skipped**. The skip is QuantLib-runtime-specific because the QuantLib wheel is unavailable in this sandbox.
- Frontend unit tests: **10 passed**.
- Python compileall: passed.
- Native C++20 kernel: compiled and executed successfully with `g++`.
- C++ benchmark workload: 50,000 exposures x 1,000 scenarios executed in 44 ms in this sandbox run (environment-specific, not a production benchmark claim).
- FastAPI live smoke: `/health`, `/portfolio`, `/risk/var`, `/risk/stress/evaluate` passed.
- Service was stopped after smoke testing; port 8000 is not left listening.
- `npm run build`: blocked because Vite is not installed locally and external npm registry access is unavailable in this sandbox. `npm test` succeeds because the unit suite uses Node's built-in test runner.
