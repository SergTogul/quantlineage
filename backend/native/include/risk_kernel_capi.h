#ifndef RISKFORGE_RISK_KERNEL_CAPI_H
#define RISKFORGE_RISK_KERNEL_CAPI_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ABI version the Python ctypes bridge must match. Bump on any incompatible
   change to argument order, strides, or error codes. */
#define RISKFORGE_KERNEL_ABI 1

#define RISKFORGE_KERNEL_EXPOSURE_STRIDE 5 /* delta, gamma, vega, dv01, fx_delta */
#define RISKFORGE_KERNEL_SHOCK_STRIDE 4    /* equity, vol_points, rates_bps, fx */

#define RISKFORGE_KERNEL_OK 0
#define RISKFORGE_KERNEL_ERR_ABI 1
#define RISKFORGE_KERNEL_ERR_NULL 2
#define RISKFORGE_KERNEL_ERR_LENGTH 3

int riskforge_kernel_abi_version(void);

/*
 * Validate ABI, pointers, and buffer lengths, then write n_shocks P&Ls.
 * P&L math is unchanged (delegates to portfolio_scenarios_flat_into).
 *
 * Length contract (else RISKFORGE_KERNEL_ERR_LENGTH, no writes):
 *   n_exposure_doubles == n_exposures * RISKFORGE_KERNEL_EXPOSURE_STRIDE
 *   n_shock_doubles    == n_shocks * RISKFORGE_KERNEL_SHOCK_STRIDE
 *   n_out              == n_shocks
 *
 * Null / empty policy:
 *   Count == 0: corresponding pointer may be NULL (no dereference).
 *   n_shocks == 0: success, no writes (out may be NULL).
 *   n_exposures == 0 && n_shocks > 0: write 0.0 per shock (empty book).
 *   Count > 0 && pointer == NULL: RISKFORGE_KERNEL_ERR_NULL (no writes).
 *
 * abi must equal RISKFORGE_KERNEL_ABI else RISKFORGE_KERNEL_ERR_ABI.
 */
int riskforge_portfolio_scenarios(
    int abi,
    const double* exposures,
    size_t n_exposures,
    size_t n_exposure_doubles,
    const double* shocks,
    size_t n_shocks,
    size_t n_shock_doubles,
    double* out,
    size_t n_out);

#ifdef __cplusplus
}
#endif

#endif /* RISKFORGE_RISK_KERNEL_CAPI_H */
