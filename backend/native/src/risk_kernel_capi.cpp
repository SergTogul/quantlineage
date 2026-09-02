#include <cstddef>
extern "C" void riskforge_portfolio_scenarios(
    const double* exposures, std::size_t n_exposures,
    const double* shocks, std::size_t n_shocks,
    double* out) {
  for (std::size_t j=0;j<n_shocks;++j) {
    const double er=shocks[j*4], vp=shocks[j*4+1], rb=shocks[j*4+2], fx=shocks[j*4+3];
    double total=0.0;
    for (std::size_t i=0;i<n_exposures;++i) {
      const double* e=&exposures[i*5];
      total += e[0]*er + 0.5*e[1]*er*er + e[2]*vp + e[3]*rb + e[4]*fx;
    }
    out[j]=total;
  }
}
