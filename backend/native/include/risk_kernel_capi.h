#ifndef QUANTLINEAGE_RISK_KERNEL_CAPI_H
#define QUANTLINEAGE_RISK_KERNEL_CAPI_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ABI version the Python ctypes bridge must match. Bump on any incompatible
   change to argument order, strides, or error codes. */
#define QUANTLINEAGE_KERNEL_ABI 1

#define QUANTLINEAGE_KERNEL_EXPOSURE_STRIDE 5 /* delta, gamma, vega, dv01, fx_delta */
#define QUANTLINEAGE_KERNEL_SHOCK_STRIDE 4    /* equity, vol_points, rates_bps, fx */

#define QUANTLINEAGE_KERNEL_OK 0
#define QUANTLINEAGE_KERNEL_ERR_ABI 1
#define QUANTLINEAGE_KERNEL_ERR_NULL 2
#define QUANTLINEAGE_KERNEL_ERR_LENGTH 3

int quantlineage_kernel_abi_version(void);

/*
 * Validate ABI, pointers, and buffer lengths, then write n_shocks P&Ls.
 * P&L math is unchanged (delegates to portfolio_scenarios_flat_into).
 *
 * Length contract (else QUANTLINEAGE_KERNEL_ERR_LENGTH, no writes):
 *   n_exposure_doubles == n_exposures * QUANTLINEAGE_KERNEL_EXPOSURE_STRIDE
 *   n_shock_doubles    == n_shocks * QUANTLINEAGE_KERNEL_SHOCK_STRIDE
 *   n_out              == n_shocks
 *
 * Null / empty policy:
 *   Count == 0: corresponding pointer may be NULL (no dereference).
 *   n_shocks == 0: success, no writes (out may be NULL).
 *   n_exposures == 0 && n_shocks > 0: write 0.0 per shock (empty book).
 *   Count > 0 && pointer == NULL: QUANTLINEAGE_KERNEL_ERR_NULL (no writes).
 *
 * abi must equal QUANTLINEAGE_KERNEL_ABI else QUANTLINEAGE_KERNEL_ERR_ABI.
 */
int quantlineage_portfolio_scenarios(
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

#endif /* QUANTLINEAGE_RISK_KERNEL_CAPI_H */
