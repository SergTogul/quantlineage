// Standalone scenario-aggregation microbenchmark.
// Reuses risk_kernel.hpp (same math / stdlib thread pool as the ctypes C ABI).
// Not a production SLA.
//
// Usage:
//   scenario_bench [--exposures N] [--shocks M] [--iters K] [--threads T] [--json]
//
// ``--threads 0`` (default) uses RISKFORGE_KERNEL_THREADS or hardware_concurrency.
// ``--threads 1`` forces the serial path (M6.2 baseline).
// Defaults: 1000 exposures × 1000 shocks × 1 iteration.

#include "risk_kernel.hpp"

#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <sys/resource.h>

namespace {

long peak_rss_kib() {
  rusage usage{};
  if (getrusage(RUSAGE_SELF, &usage) != 0) {
    return -1;
  }
#if defined(__APPLE__)
  // macOS reports ru_maxrss in bytes.
  return static_cast<long>(usage.ru_maxrss / 1024);
#else
  // Linux reports ru_maxrss in kilobytes.
  return static_cast<long>(usage.ru_maxrss);
#endif
}

void print_usage(const char* argv0) {
  std::cerr << "Usage: " << argv0
            << " [--exposures N] [--shocks M] [--iters K] [--threads T] [--json]\n"
            << "  --threads T   0=auto (env/hw), 1=serial, >1=stdlib thread pool\n";
}

}  // namespace

int main(int argc, char** argv) {
  using namespace riskforge;
  std::size_t n_exposures = 1000;
  std::size_t n_shocks = 1000;
  int iters = 1;
  unsigned threads = 0;  // auto
  bool json = false;

  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--exposures") == 0 && i + 1 < argc) {
      n_exposures = static_cast<std::size_t>(std::strtoull(argv[++i], nullptr, 10));
    } else if (std::strcmp(argv[i], "--shocks") == 0 && i + 1 < argc) {
      n_shocks = static_cast<std::size_t>(std::strtoull(argv[++i], nullptr, 10));
    } else if (std::strcmp(argv[i], "--iters") == 0 && i + 1 < argc) {
      iters = static_cast<int>(std::strtol(argv[++i], nullptr, 10));
    } else if (std::strcmp(argv[i], "--threads") == 0 && i + 1 < argc) {
      threads = static_cast<unsigned>(std::strtoul(argv[++i], nullptr, 10));
    } else if (std::strcmp(argv[i], "--json") == 0) {
      json = true;
    } else if (std::strcmp(argv[i], "--help") == 0 || std::strcmp(argv[i], "-h") == 0) {
      print_usage(argv[0]);
      return 0;
    } else {
      print_usage(argv[0]);
      return 2;
    }
  }

  if (iters < 1 || n_exposures == 0 || n_shocks == 0) {
    std::cerr << "exposures, shocks, and iters must be >= 1\n";
    return 2;
  }

  std::vector<Exposure> exposures(n_exposures, {1000.0, 200.0, 30.0, -10.0, 500.0});
  std::vector<Shock> shocks(n_shocks, {-0.01, 2.0, 5.0, -0.002});
  const unsigned resolved = resolve_kernel_threads(threads);

  // Warmup (excluded from timed region).
  volatile double sink = portfolio_scenarios(exposures, shocks, threads)[0];
  (void)sink;

  auto t0 = std::chrono::steady_clock::now();
  std::vector<double> out;
  for (int k = 0; k < iters; ++k) {
    out = portfolio_scenarios(exposures, shocks, threads);
  }
  auto t1 = std::chrono::steady_clock::now();

  const double elapsed_ms =
      std::chrono::duration<double, std::milli>(t1 - t0).count();
  const double elapsed_s = elapsed_ms / 1000.0;
  const double ops = static_cast<double>(n_exposures) * static_cast<double>(n_shocks) *
                     static_cast<double>(iters);
  const double throughput_ops_s = elapsed_s > 0.0 ? ops / elapsed_s : 0.0;
  const double scenarios_per_s =
      elapsed_s > 0.0 ? (static_cast<double>(n_shocks) * iters) / elapsed_s : 0.0;
  const long rss_kib = peak_rss_kib();
  const double checksum = out.empty() ? 0.0 : out[0];

  if (json) {
    std::cout << "{"
              << "\"impl\":\"cpp_header\","
              << "\"n_exposures\":" << n_exposures << ","
              << "\"n_shocks\":" << n_shocks << ","
              << "\"iters\":" << iters << ","
              << "\"threads_requested\":" << threads << ","
              << "\"threads_resolved\":" << resolved << ","
              << "\"parallel_strategy\":\"std_thread_shock_partition\","
              << "\"has_jthread\":" << (RISKFORGE_HAS_JTHREAD ? "true" : "false") << ","
              << "\"wall_ms\":" << elapsed_ms << ","
              << "\"throughput_ops_per_s\":" << throughput_ops_s << ","
              << "\"scenarios_per_s\":" << scenarios_per_s << ","
              << "\"peak_rss_kib\":" << rss_kib << ","
              << "\"checksum\":" << checksum
              << "}\n";
  } else {
    std::cout << "impl=cpp_header"
              << " exposures=" << n_exposures
              << " shocks=" << n_shocks
              << " iters=" << iters
              << " threads_requested=" << threads
              << " threads_resolved=" << resolved
              << " parallel_strategy=std_thread_shock_partition"
              << " has_jthread=" << (RISKFORGE_HAS_JTHREAD ? 1 : 0)
              << " wall_ms=" << elapsed_ms
              << " throughput_ops_per_s=" << throughput_ops_s
              << " scenarios_per_s=" << scenarios_per_s
              << " peak_rss_kib=" << rss_kib
              << " checksum=" << checksum
              << "\n";
  }
  return 0;
}
