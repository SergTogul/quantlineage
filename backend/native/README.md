# Native scenario kernel

Build the optional shared library:

```bash
g++ -std=c++20 -O3 -shared -fPIC src/risk_kernel_capi.cpp -o libriskkernel.so
```

`app.compute.kernel.NativeScenarioKernel` loads it with Python `ctypes`; no pybind11 dependency is required. The risk/business layers remain independent of the kernel.
