#pragma once

// RiskForge scenario aggregation kernel (M6).
//
// Parallel strategy (M6.4 / R0.17): ONE approach only — C++20 standard-library
// thread pool over contiguous shock partitions (std::jthread when available,
// else std::thread + join-on-scope-exit). Serial when workers<=1, n_shocks<=1,
// or n_exposures*n_shocks < KERNEL_PARALLEL_MIN_WORK (tiny workloads do not
// spawn threads). Not OpenMP. Do not mix strategies.
//
// Each out[j] is written by exactly one thread; inner exposure reduction order
// matches the single-thread loop for numerical parity.

#include <algorithm>
#include <cstddef>
#include <cstdlib>
#include <limits>
#include <thread>
#include <vector>

#if defined(__cpp_lib_jthread) && __cpp_lib_jthread >= 201911L
#define RISKFORGE_HAS_JTHREAD 1
#else
#define RISKFORGE_HAS_JTHREAD 0
#endif

namespace riskforge {

struct Exposure {
  double delta, gamma, vega, dv01, fx_delta;
};
struct Shock {
  double equity_return, vol_points, rates_bps, fx_return;
};

/// Env override for auto thread count: RISKFORGE_KERNEL_THREADS (unsigned > 0).
inline constexpr const char* KERNEL_THREADS_ENV = "RISKFORGE_KERNEL_THREADS";

/// Below this E×S product the kernel stays serial (R0.17). Avoids per-call
/// thread spawn on tiny books / short histories. Must match Python
/// ``KERNEL_PARALLEL_MIN_WORK``.
inline constexpr std::size_t KERNEL_PARALLEL_MIN_WORK = 4096;

inline bool kernel_work_is_tiny(std::size_t n_exposures, std::size_t n_shocks) noexcept {
  if (n_shocks <= 1 || n_exposures == 0) {
    return true;
  }
  if (n_exposures > (std::numeric_limits<std::size_t>::max() / n_shocks)) {
    return false;
  }
  return n_exposures * n_shocks < KERNEL_PARALLEL_MIN_WORK;
}

inline bool kernel_use_serial(std::size_t n_exposures, std::size_t n_shocks,
                             unsigned workers) noexcept {
  return workers <= 1 || kernel_work_is_tiny(n_exposures, n_shocks);
}

/// Test observability: last ``portfolio_scenarios_*_into`` used worker threads.
inline bool& kernel_last_used_workers_flag() noexcept {
  static bool flag = false;
  return flag;
}

inline double scenario_pnl(const Exposure& e, const Shock& s) noexcept {
  return e.delta * s.equity_return + 0.5 * e.gamma * s.equity_return * s.equity_return +
         e.vega * s.vol_points + e.dv01 * s.rates_bps + e.fx_delta * s.fx_return;
}

inline unsigned hardware_threads_or_1() noexcept {
  const unsigned hc = std::thread::hardware_concurrency();
  return hc == 0 ? 1u : hc;
}

/// Resolve worker count. ``requested == 0`` → env ``RISKFORGE_KERNEL_THREADS`` if set,
/// else ``std::thread::hardware_concurrency()`` (minimum 1).
inline unsigned resolve_kernel_threads(unsigned requested = 0) noexcept {
  if (requested > 0) {
    return requested;
  }
  if (const char* env = std::getenv(KERNEL_THREADS_ENV)) {
    if (env[0] != '\0') {
      char* end = nullptr;
      const unsigned long parsed = std::strtoul(env, &end, 10);
      if (end != env && parsed > 0UL && parsed <= 4096UL) {
        return static_cast<unsigned>(parsed);
      }
    }
  }
  return hardware_threads_or_1();
}

inline void shock_partition(std::size_t n_shocks, unsigned n_threads, unsigned tid,
                            std::size_t& begin, std::size_t& end) noexcept {
  const std::size_t chunk = n_shocks / n_threads;
  const std::size_t rem = n_shocks % n_threads;
  begin = tid * chunk + std::min<std::size_t>(tid, rem);
  end = begin + chunk + (tid < rem ? 1u : 0u);
}

inline void portfolio_scenarios_serial_into(const Exposure* exposures, std::size_t n_exposures,
                                            const Shock* shocks, std::size_t n_shocks,
                                            double* out) noexcept {
  for (std::size_t j = 0; j < n_shocks; ++j) {
    double total = 0.0;
    for (std::size_t i = 0; i < n_exposures; ++i) {
      total += scenario_pnl(exposures[i], shocks[j]);
    }
    out[j] = total;
  }
}

inline void portfolio_scenarios_flat_serial_into(const double* exposures, std::size_t n_exposures,
                                                 const double* shocks, std::size_t n_shocks,
                                                 double* out) noexcept {
  for (std::size_t j = 0; j < n_shocks; ++j) {
    const double er = shocks[j * 4];
    const double vp = shocks[j * 4 + 1];
    const double rb = shocks[j * 4 + 2];
    const double fx = shocks[j * 4 + 3];
    double total = 0.0;
    for (std::size_t i = 0; i < n_exposures; ++i) {
      const double* e = &exposures[i * 5];
      total += e[0] * er + 0.5 * e[1] * er * er + e[2] * vp + e[3] * rb + e[4] * fx;
    }
    out[j] = total;
  }
}

/// Parallel (or serial) portfolio scenarios. ``n_threads == 0`` uses
/// :func:`resolve_kernel_threads`. Shock ranges are disjoint; no atomics.
inline void portfolio_scenarios_into(const Exposure* exposures, std::size_t n_exposures,
                                     const Shock* shocks, std::size_t n_shocks, double* out,
                                     unsigned n_threads = 0) {
  const unsigned workers = resolve_kernel_threads(n_threads);
  if (kernel_use_serial(n_exposures, n_shocks, workers)) {
    kernel_last_used_workers_flag() = false;
    portfolio_scenarios_serial_into(exposures, n_exposures, shocks, n_shocks, out);
    return;
  }
  kernel_last_used_workers_flag() = true;
  const unsigned use = static_cast<unsigned>(
      std::min<std::size_t>(workers, n_shocks));
#if RISKFORGE_HAS_JTHREAD
  std::vector<std::jthread> pool;
  pool.reserve(use);
  for (unsigned tid = 0; tid < use; ++tid) {
    std::size_t begin = 0, end = 0;
    shock_partition(n_shocks, use, tid, begin, end);
    pool.emplace_back([=]() noexcept {
      for (std::size_t j = begin; j < end; ++j) {
        double total = 0.0;
        for (std::size_t i = 0; i < n_exposures; ++i) {
          total += scenario_pnl(exposures[i], shocks[j]);
        }
        out[j] = total;
      }
    });
  }
#else
  std::vector<std::thread> pool;
  pool.reserve(use);
  for (unsigned tid = 0; tid < use; ++tid) {
    std::size_t begin = 0, end = 0;
    shock_partition(n_shocks, use, tid, begin, end);
    pool.emplace_back([=]() noexcept {
      for (std::size_t j = begin; j < end; ++j) {
        double total = 0.0;
        for (std::size_t i = 0; i < n_exposures; ++i) {
          total += scenario_pnl(exposures[i], shocks[j]);
        }
        out[j] = total;
      }
    });
  }
  for (auto& t : pool) {
    t.join();
  }
#endif
}

inline void portfolio_scenarios_flat_into(const double* exposures, std::size_t n_exposures,
                                          const double* shocks, std::size_t n_shocks, double* out,
                                          unsigned n_threads = 0) {
  const unsigned workers = resolve_kernel_threads(n_threads);
  if (kernel_use_serial(n_exposures, n_shocks, workers)) {
    kernel_last_used_workers_flag() = false;
    portfolio_scenarios_flat_serial_into(exposures, n_exposures, shocks, n_shocks, out);
    return;
  }
  kernel_last_used_workers_flag() = true;
  const unsigned use = static_cast<unsigned>(
      std::min<std::size_t>(workers, n_shocks));
#if RISKFORGE_HAS_JTHREAD
  std::vector<std::jthread> pool;
  pool.reserve(use);
  for (unsigned tid = 0; tid < use; ++tid) {
    std::size_t begin = 0, end = 0;
    shock_partition(n_shocks, use, tid, begin, end);
    pool.emplace_back([=]() noexcept {
      for (std::size_t j = begin; j < end; ++j) {
        const double er = shocks[j * 4];
        const double vp = shocks[j * 4 + 1];
        const double rb = shocks[j * 4 + 2];
        const double fx = shocks[j * 4 + 3];
        double total = 0.0;
        for (std::size_t i = 0; i < n_exposures; ++i) {
          const double* e = &exposures[i * 5];
          total += e[0] * er + 0.5 * e[1] * er * er + e[2] * vp + e[3] * rb + e[4] * fx;
        }
        out[j] = total;
      }
    });
  }
#else
  std::vector<std::thread> pool;
  pool.reserve(use);
  for (unsigned tid = 0; tid < use; ++tid) {
    std::size_t begin = 0, end = 0;
    shock_partition(n_shocks, use, tid, begin, end);
    pool.emplace_back([=]() noexcept {
      for (std::size_t j = begin; j < end; ++j) {
        const double er = shocks[j * 4];
        const double vp = shocks[j * 4 + 1];
        const double rb = shocks[j * 4 + 2];
        const double fx = shocks[j * 4 + 3];
        double total = 0.0;
        for (std::size_t i = 0; i < n_exposures; ++i) {
          const double* e = &exposures[i * 5];
          total += e[0] * er + 0.5 * e[1] * er * er + e[2] * vp + e[3] * rb + e[4] * fx;
        }
        out[j] = total;
      }
    });
  }
  for (auto& t : pool) {
    t.join();
  }
#endif
}

inline std::vector<double> portfolio_scenarios(const std::vector<Exposure>& ex,
                                               const std::vector<Shock>& shocks,
                                               unsigned n_threads = 0) {
  std::vector<double> out(shocks.size(), 0.0);
  if (shocks.empty()) {
    return out;
  }
  portfolio_scenarios_into(ex.data(), ex.size(), shocks.data(), shocks.size(), out.data(),
                           n_threads);
  return out;
}

}  // namespace riskforge
