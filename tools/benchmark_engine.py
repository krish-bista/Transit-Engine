"""
Transit Engine Routing Performance & Latency Benchmark Harness.
Measures execution throughput (QPS), percentiles (p50, p90, p95, p99), cache performance, and concurrency scaling.
"""

import os
import sys
import time
import json
import random
import statistics
import argparse
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Tuple

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from gateway.gtfs_data import GTFSDataManager
    from gateway.raptor_engine import RaptorEngine
except ImportError:
    from gtfs_data import GTFSDataManager
    from raptor_engine import RaptorEngine


class BenchmarkRunner:
    """Benchmark runner for the RAPTOR routing algorithm."""

    def __init__(self, data_manager: Optional[GTFSDataManager] = None, raptor_engine: Optional[RaptorEngine] = None):
        self.dm = data_manager or GTFSDataManager()
        self.engine = raptor_engine or RaptorEngine(
            self.dm.stops, self.dm.stop_times, self.dm.routes, self.dm.trips
        )
        if isinstance(self.dm.stops, dict):
            self.stop_ids = [int(k) for k in self.dm.stops.keys()]
        else:
            self.stop_ids = [s["id"] if isinstance(s, dict) and "id" in s else i for i, s in enumerate(self.dm.stops)]

    def generate_random_queries(self, count: int, departure_sec_range: Tuple[int, int] = (25200, 64800)) -> List[Tuple[int, int, int]]:
        """Generate (source_id, target_id, dep_sec) query triplets."""
        if len(self.stop_ids) < 2:
            return []
        
        queries = []
        for _ in range(count):
            src, dst = random.sample(self.stop_ids, 2)
            dep = random.randint(departure_sec_range[0], departure_sec_range[1])
            queries.append((src, dst, dep))
        return queries

    def execute_single_query(self, query: Tuple[int, int, int]) -> Dict[str, Any]:
        """Execute single routing plan and record fine-grained performance."""
        src, dst, dep = query
        t0 = time.perf_counter()
        result = self.engine.plan_route(src, dst, dep)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        found = result is not None and len(result) > 0
        legs_count = len(result) if found else 0
        transfers = max(0, sum(1 for leg in result if leg.get("route_id") != "WALK") - 1) if found else 0

        return {
            "source": src,
            "target": dst,
            "departure_sec": dep,
            "latency_ms": latency_ms,
            "found": found,
            "legs": legs_count,
            "transfers": transfers,
        }

    def run_benchmark(
        self,
        num_queries: int = 100,
        concurrency: int = 1,
        warmup_queries: int = 10,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Execute full benchmark suite with statistical aggregation."""
        random.seed(seed)
        
        # Warm-up run to eliminate JIT / caching discrepancies
        warmup_sample = self.generate_random_queries(warmup_queries)
        for q in warmup_sample:
            self.execute_single_query(q)

        # Generate test queries
        queries = self.generate_random_queries(num_queries)
        if not queries:
            return {"error": "Insufficient stops data for benchmarking"}

        start_time = time.perf_counter()
        results: List[Dict[str, Any]] = []

        if concurrency <= 1:
            for q in queries:
                results.append(self.execute_single_query(q))
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                results = list(executor.map(self.execute_single_query, queries))

        total_duration_sec = time.perf_counter() - start_time
        latencies = [r["latency_ms"] for r in results]
        found_count = sum(1 for r in results if r["found"])

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)

        p50 = sorted_lat[int(n * 0.50)]
        p90 = sorted_lat[min(n - 1, int(n * 0.90))]
        p95 = sorted_lat[min(n - 1, int(n * 0.95))]
        p99 = sorted_lat[min(n - 1, int(n * 0.99))]

        mean_lat = statistics.mean(latencies) if latencies else 0.0
        std_lat = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
        qps = round(num_queries / total_duration_sec, 2) if total_duration_sec > 0 else 0.0

        summary = {
            "num_queries": num_queries,
            "concurrency": concurrency,
            "total_duration_sec": round(total_duration_sec, 3),
            "throughput_qps": qps,
            "success_rate_pct": round((found_count / num_queries) * 100, 2),
            "latency_ms": {
                "min": round(min(latencies), 3),
                "mean": round(mean_lat, 3),
                "std": round(std_lat, 3),
                "p50": round(p50, 3),
                "p90": round(p90, 3),
                "p95": round(p95, 3),
                "p99": round(p99, 3),
                "max": round(max(latencies), 3),
            },
            "network_stats": {
                "total_stops": len(self.dm.stops),
                "total_routes": len(self.engine.routes),
                "total_trips": len(self.dm.trips),
            }
        }
        return summary

    def format_markdown_report(self, summary: Dict[str, Any]) -> str:
        """Format benchmark summary into clean Markdown table."""
        l = summary["latency_ms"]
        n = summary["network_stats"]

        return f"""# 🚀 Transit Engine RAPTOR Benchmark Report

## 📊 Summary
- **Total Queries**: `{summary['num_queries']}`
- **Concurrency**: `{summary['concurrency']} threads`
- **Total Duration**: `{summary['total_duration_sec']}s`
- **Throughput**: **`{summary['throughput_qps']} QPS`**
- **Route Success Rate**: `{summary['success_rate_pct']}%`

## ⏱️ Latency Distribution (ms)
| Metric | Latency (ms) |
|---|---|
| **Min** | `{l['min']} ms` |
| **Mean** | `{l['mean']} ms` (± `{l['std']}`) |
| **P50 (Median)** | **`{l['p50']} ms`** |
| **P90** | `{l['p90']} ms` |
| **P95** | **`{l['p95']} ms`** |
| **P99** | `{l['p99']} ms` |
| **Max** | `{l['max']} ms` |

## 🗺️ Network Topology
- **Stops Loaded**: `{n['total_stops']}`
- **Routes Loaded**: `{n['total_routes']}`
- **Trips Indexed**: `{n['total_trips']}`
"""


def main():
    parser = argparse.ArgumentParser(description="Transit Engine Performance Benchmark Suite")
    parser.add_argument("--queries", type=int, default=100, help="Number of queries to benchmark (default: 100)")
    parser.add_argument("--concurrency", type=int, default=1, help="Thread concurrency level (default: 1)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON results path")
    parser.add_argument("--markdown", type=str, default=None, help="Output Markdown report path")
    args = parser.parse_args()

    print(f"[*] Initializing Transit Engine RAPTOR Benchmark Suite...")
    runner = BenchmarkRunner()
    print(f"[*] Loaded {len(runner.dm.stops)} stops, {len(runner.engine.routes)} routes.")
    print(f"[*] Running {args.queries} queries with concurrency={args.concurrency}...")

    summary = runner.run_benchmark(num_queries=args.queries, concurrency=args.concurrency)

    print("\n" + "=" * 50)
    print(f"Throughput:    {summary['throughput_qps']} QPS")
    print(f"Success Rate:  {summary['success_rate_pct']}%")
    print(f"P50 Latency:   {summary['latency_ms']['p50']} ms")
    print(f"P95 Latency:   {summary['latency_ms']['p95']} ms")
    print(f"P99 Latency:   {summary['latency_ms']['p99']} ms")
    print(f"Max Latency:   {summary['latency_ms']['max']} ms")
    print("=" * 50)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"[+] JSON results written to {args.output}")

    if args.markdown:
        md_text = runner.format_markdown_report(summary)
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"[+] Markdown report written to {args.markdown}")


if __name__ == "__main__":
    main()
