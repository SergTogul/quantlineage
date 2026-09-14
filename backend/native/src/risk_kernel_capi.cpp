#include "risk_kernel_capi.h"
#include "risk_kernel.hpp"

#include <limits>

// C ABI for ctypes. Parallelism lives only in risk_kernel.hpp (stdlib thread
// pool over shock partitions; jthread when available, else std::thread+join).
// No OpenMP. Thread count: QUANTLINEAGE_KERNEL_THREADS or hw.
//
// R0.12.5: version + error return + length/null checks before any buffer walk.
// P&L math is unchanged (portfolio_scenarios_flat_into).

extern "C" int quantlineage_kernel_abi_version(void) {
  return QUANTLINEAGE_KERNEL_ABI;
}

extern "C" int quantlineage_portfolio_scenarios(
    int abi,
    const double* exposures,
    std::size_t n_exposures,
    std::size_t n_exposure_doubles,
    const double* shocks,
    std::size_t n_shocks,
    std::size_t n_shock_doubles,
    double* out,
    std::size_t n_out) {
  if (abi != QUANTLINEAGE_KERNEL_ABI) {
    return QUANTLINEAGE_KERNEL_ERR_ABI;
  }

  constexpr std::size_t kMax = std::numeric_limits<std::size_t>::max();
  if (n_exposures > kMax / QUANTLINEAGE_KERNEL_EXPOSURE_STRIDE ||
      n_shocks > kMax / QUANTLINEAGE_KERNEL_SHOCK_STRIDE) {
    return QUANTLINEAGE_KERNEL_ERR_LENGTH;
  }
  const std::size_t exp_need = n_exposures * static_cast<std::size_t>(QUANTLINEAGE_KERNEL_EXPOSURE_STRIDE);
  const std::size_t shk_need = n_shocks * static_cast<std::size_t>(QUANTLINEAGE_KERNEL_SHOCK_STRIDE);
  if (n_exposure_doubles != exp_need || n_shock_doubles != shk_need || n_out != n_shocks) {
    return QUANTLINEAGE_KERNEL_ERR_LENGTH;
  }

  if (n_exposures > 0 && exposures == nullptr) {
    return QUANTLINEAGE_KERNEL_ERR_NULL;
  }
  if (n_shocks > 0 && (shocks == nullptr || out == nullptr)) {
    return QUANTLINEAGE_KERNEL_ERR_NULL;
  }

  if (n_shocks == 0) {
    return QUANTLINEAGE_KERNEL_OK;
  }

  quantlineage::portfolio_scenarios_flat_into(exposures, n_exposures, shocks, n_shocks, out,
                                           /*n_threads=*/0);
  return QUANTLINEAGE_KERNEL_OK;
}
