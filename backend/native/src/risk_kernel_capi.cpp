#include "risk_kernel.hpp"

#include <cstddef>

// C ABI for ctypes. Parallelism lives only in risk_kernel.hpp (stdlib thread
// pool over shock partitions; jthread when available, else std::thread+join).
// No OpenMP. Thread count: RISKFORGE_KERNEL_THREADS or hw.

extern "C" void riskforge_portfolio_scenarios(
    const double* exposures, std::size_t n_exposures,
    const double* shocks, std::size_t n_shocks,
    double* out) {
  riskforge::portfolio_scenarios_flat_into(exposures, n_exposures, shocks, n_shocks, out,
                                           /*n_threads=*/0);
}
