import pytest
from tools.benchmark_engine import BenchmarkRunner

def test_benchmark_runner_generation():
    runner = BenchmarkRunner()
    queries = runner.generate_random_queries(5)
    assert len(queries) == 5
    for src, dst, dep in queries:
        assert isinstance(src, int)
        assert isinstance(dst, int)
        assert src != dst
        assert 0 <= dep <= 86400

def test_benchmark_runner_single_query():
    runner = BenchmarkRunner()
    queries = runner.generate_random_queries(1)
    if queries:
        result = runner.execute_single_query(queries[0])
        assert "source" in result
        assert "target" in result
        assert "latency_ms" in result
        assert result["latency_ms"] >= 0.0

def test_benchmark_runner_run_suite():
    runner = BenchmarkRunner()
    summary = runner.run_benchmark(num_queries=10, concurrency=2, warmup_queries=2, seed=123)
    assert summary["num_queries"] == 10
    assert summary["concurrency"] == 2
    assert "throughput_qps" in summary
    assert "latency_ms" in summary
    assert summary["latency_ms"]["p50"] >= 0.0
    assert summary["latency_ms"]["max"] >= summary["latency_ms"]["min"]

    # Test Markdown formatting
    md = runner.format_markdown_report(summary)
    assert "# 🚀 Transit Engine RAPTOR Benchmark Report" in md
    assert "Throughput" in md
