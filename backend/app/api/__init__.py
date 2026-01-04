"""HTTP API routers (Backend/API Engineer ownership).

M7.1 modules: health, portfolio, market, risk, stress, attribution, limits, risk_runs.
M7.2: dual-mounted at legacy paths and ``/api/v1/...`` from ``app.main``.
M7.5: consistent error envelope via ``app.api.errors.register_exception_handlers``.
"""
