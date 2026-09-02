#pragma once
#include <cstddef>
#include <vector>

namespace riskforge {
struct Exposure { double delta, gamma, vega, dv01, fx_delta; };
struct Shock { double equity_return, vol_points, rates_bps, fx_return; };

inline double scenario_pnl(const Exposure& e, const Shock& s) noexcept {
    return e.delta*s.equity_return + 0.5*e.gamma*s.equity_return*s.equity_return
         + e.vega*s.vol_points + e.dv01*s.rates_bps + e.fx_delta*s.fx_return;
}

inline std::vector<double> portfolio_scenarios(const std::vector<Exposure>& ex,
                                                const std::vector<Shock>& shocks) {
    std::vector<double> out(shocks.size(), 0.0);
    for (std::size_t j=0;j<shocks.size();++j)
        for (const auto& e: ex) out[j] += scenario_pnl(e, shocks[j]);
    return out;
}
}
