import os

# Unit/API tests must not depend on an optional native QuantLib wheel being
# present in the execution environment. QuantLib has its own adapter tests.
os.environ.setdefault("RISKFORGE_PRICING_ENGINE", "builtin")
