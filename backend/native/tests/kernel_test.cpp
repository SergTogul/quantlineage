#include "risk_kernel.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
int main(){
  using namespace riskforge;
  Exposure e{1000,200,30,-10,500}; Shock s{-0.1,5,20,-0.02};
  const double expected=1000*(-.1)+.5*200*.01+30*5-10*20+500*(-.02);
  assert(std::abs(scenario_pnl(e,s)-expected)<1e-12);
  auto x=portfolio_scenarios({e,e},{s}); assert(std::abs(x[0]-2*expected)<1e-12);
  std::cout << "risk_kernel_ok\n";
}
