#include "risk_kernel.hpp"

#include <cassert>
#include <cmath>
#include <iostream>
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
  shocks.reserve(128);
  for (int k = 0; k < 128; ++k) {
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

  std::cout << "risk_kernel_ok\n";
}
