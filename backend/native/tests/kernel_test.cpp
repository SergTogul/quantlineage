#include "risk_kernel.hpp"
#include "risk_kernel_capi.h"

#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
#include <vector>

int main() {
  using namespace riskforge;
  Exposure e{1000, 200, 30, -10, 500};
  Shock s{-0.1, 5, 20, -0.02};
  const double expected =
      1000 * (-.1) + .5 * 200 * .01 + 30 * 5 - 10 * 20 + 500 * (-.02);
  assert(std::abs(scenario_pnl(e, s) - expected) < 1e-12);

  auto x = portfolio_scenarios({e, e}, {s}, /*n_threads=*/1);
  assert(std::abs(x[0] - 2 * expected) < 1e-12);

  // M6.4: multi-thread vs serial numerical parity (disjoint shock writes).
  std::vector<Exposure> exposures = {
      e, { -300, 80, 10, 5, -200 }, { 50, -10, 2, 1, 25 }, e};
  std::vector<Shock> shocks;
  shocks.reserve(2048);
  for (int k = 0; k < 2048; ++k) {
    const double t = static_cast<double>(k);
    shocks.push_back(Shock{-0.01 + 0.0001 * t, 2.0 - 0.01 * t, 5.0 + 0.1 * t,
                           -0.002 + 0.00005 * t});
  }
  const auto serial = portfolio_scenarios(exposures, shocks, /*n_threads=*/1);
  for (unsigned thr : {2u, 3u, 4u, 7u, 8u}) {
    const auto parallel = portfolio_scenarios(exposures, shocks, thr);
    assert(parallel.size() == serial.size());
    for (std::size_t j = 0; j < serial.size(); ++j) {
      assert(std::abs(parallel[j] - serial[j]) < 1e-12);
    }
  }

  // Flat ABI path parity (same as ctypes).
  std::vector<double> eflat;
  eflat.reserve(exposures.size() * 5);
  for (const auto& ex : exposures) {
    eflat.push_back(ex.delta);
    eflat.push_back(ex.gamma);
    eflat.push_back(ex.vega);
    eflat.push_back(ex.dv01);
    eflat.push_back(ex.fx_delta);
  }
  std::vector<double> sflat;
  sflat.reserve(shocks.size() * 4);
  for (const auto& sh : shocks) {
    sflat.push_back(sh.equity_return);
    sflat.push_back(sh.vol_points);
    sflat.push_back(sh.rates_bps);
    sflat.push_back(sh.fx_return);
  }
  std::vector<double> flat_serial(shocks.size());
  std::vector<double> flat_par(shocks.size());
  portfolio_scenarios_flat_into(eflat.data(), exposures.size(), sflat.data(), shocks.size(),
                                flat_serial.data(), 1);
  portfolio_scenarios_flat_into(eflat.data(), exposures.size(), sflat.data(), shocks.size(),
                                flat_par.data(), 4);
  for (std::size_t j = 0; j < shocks.size(); ++j) {
    assert(std::abs(flat_serial[j] - serial[j]) < 1e-12);
    assert(std::abs(flat_par[j] - serial[j]) < 1e-12);
  }

  // R0.12.5: C ABI version, length, and null/empty policy (fail closed).
  assert(RISKFORGE_KERNEL_ABI == 1);
  assert(riskforge_kernel_abi_version() == RISKFORGE_KERNEL_ABI);

  double one_e[] = {1000.0, 200.0, 30.0, -10.0, 500.0};
  double one_s[] = {-0.1, 5.0, 20.0, -0.02};
  double abi_out = 99.0;
  int rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, 5, one_s, 1, 4,
                                         &abi_out, 1);
  assert(rc == RISKFORGE_KERNEL_OK);
  assert(std::abs(abi_out - expected) < 1e-12);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(/*abi=*/0, one_e, 1, 5, one_s, 1, 4, &abi_out, 1);
  assert(rc == RISKFORGE_KERNEL_ERR_ABI);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, /*n_exposure_doubles=*/4,
                                     one_s, 1, 4, &abi_out, 1);
  assert(rc == RISKFORGE_KERNEL_ERR_LENGTH);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, 5, one_s, 1,
                                     /*n_shock_doubles=*/3, &abi_out, 1);
  assert(rc == RISKFORGE_KERNEL_ERR_LENGTH);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, 5, one_s, 1, 4, &abi_out,
                                     /*n_out=*/0);
  assert(rc == RISKFORGE_KERNEL_ERR_LENGTH);
  assert(abi_out == 99.0);

  // Wrap-sized counts: *5 / *4 would wrap if the overflow guard is deleted.
  // Do not allocate wrap-sized buffers; pass the wrapped product as n_*_doubles
  // so a missing guard would treat the length as matching and walk huge n_*.
  const std::size_t wrap_exposures =
      std::numeric_limits<std::size_t>::max() / RISKFORGE_KERNEL_EXPOSURE_STRIDE + 1;
  const std::size_t wrap_shocks =
      std::numeric_limits<std::size_t>::max() / RISKFORGE_KERNEL_SHOCK_STRIDE + 1;
  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, wrap_exposures,
                                     /*n_exposure_doubles=*/4, one_s, 1, 4, &abi_out, 1);
  assert(rc == RISKFORGE_KERNEL_ERR_LENGTH);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, 5, one_s, wrap_shocks,
                                     /*n_shock_doubles=*/0, &abi_out, wrap_shocks);
  assert(rc == RISKFORGE_KERNEL_ERR_LENGTH);
  assert(abi_out == 99.0);

  // Tight buffers: a skipped length predicate overruns under ASan, not only rc.
  double two_s[] = {-0.1, 5.0, 20.0, -0.02, 0.03, -2.0, -10.0, 0.01};
  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, 5, two_s, /*n_shocks=*/2, 8,
                                     &abi_out, /*n_out=*/1);
  assert(rc == RISKFORGE_KERNEL_ERR_LENGTH);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, /*n_exposures=*/2, 5, one_s, 1,
                                     4, &abi_out, 1);
  assert(rc == RISKFORGE_KERNEL_ERR_LENGTH);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, nullptr, 1, 5, one_s, 1, 4, &abi_out,
                                     1);
  assert(rc == RISKFORGE_KERNEL_ERR_NULL);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, 5, nullptr, 1, 4, &abi_out,
                                     1);
  assert(rc == RISKFORGE_KERNEL_ERR_NULL);
  assert(abi_out == 99.0);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, one_e, 1, 5, one_s, 1, 4, nullptr, 1);
  assert(rc == RISKFORGE_KERNEL_ERR_NULL);
  assert(abi_out == 99.0);

  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, nullptr, 0, 0, nullptr, 0, 0, nullptr,
                                     0);
  assert(rc == RISKFORGE_KERNEL_OK);

  abi_out = 99.0;
  rc = riskforge_portfolio_scenarios(RISKFORGE_KERNEL_ABI, nullptr, 0, 0, one_s, 1, 4, &abi_out,
                                     1);
  assert(rc == RISKFORGE_KERNEL_OK);
  assert(abi_out == 0.0);

  // R0.17: tiny E×S stays serial (no per-call thread spawn) even if workers > 1.
  assert(KERNEL_PARALLEL_MIN_WORK == 4096);
  assert(kernel_work_is_tiny(1, 8));
  assert(kernel_work_is_tiny(4, 256));
  assert(kernel_work_is_tiny(0, 10000));
  assert(!kernel_work_is_tiny(4, 2048));
  assert(kernel_use_serial(4, 2048, 1));
  assert(!kernel_use_serial(4, 2048, 4));

  std::vector<double> tiny_e = {1000.0, 200.0, 30.0, -10.0, 500.0};
  std::vector<double> tiny_s = {-0.1, 5.0, 20.0, -0.02, 0.03, -2.0, -10.0, 0.01};
  std::vector<double> tiny_out(2, 99.0);
  kernel_last_used_workers_flag() = true;
  portfolio_scenarios_flat_into(tiny_e.data(), 1, tiny_s.data(), 2, tiny_out.data(), 8);
  assert(!kernel_last_used_workers_flag());

  std::vector<double> large_out(shocks.size(), 0.0);
  kernel_last_used_workers_flag() = false;
  portfolio_scenarios_flat_into(eflat.data(), exposures.size(), sflat.data(), shocks.size(),
                                large_out.data(), 4);
  assert(kernel_last_used_workers_flag());
  for (std::size_t j = 0; j < serial.size(); ++j) {
    assert(std::abs(large_out[j] - serial[j]) < 1e-12);
  }

  std::cout << "risk_kernel_ok\n";
}
