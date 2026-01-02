#include "risk_kernel.hpp"
#include <chrono>
#include <iostream>
int main(){
  using namespace riskforge;
  std::vector<Exposure> e(50000,{1000,200,30,-10,500});
  std::vector<Shock> s(1000,{-0.01,2,5,-0.002});
  auto t0=std::chrono::steady_clock::now(); auto out=portfolio_scenarios(e,s); auto t1=std::chrono::steady_clock::now();
  std::cout << "scenarios="<<out.size()<<" elapsed_ms="<<std::chrono::duration_cast<std::chrono::milliseconds>(t1-t0).count()<<" checksum="<<out[0]<<"\n";
}
