"""
Prometheus and structured runtime metrics collector for Transit Engine Gateway.
Zero-dependency, thread-safe, high-performance metric aggregation.
"""

import time
import threading
from typing import Dict, Any, List


class MetricsCollector:
    """Collects and formats operational telemetry for Prometheus scraping."""

    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        
        # Request counts: (method, endpoint, status_code) -> count
        self.request_counts: Dict[str, int] = {}
        
        # Routing counts
        self.routing_success_count = 0
        self.routing_not_found_count = 0
        self.routing_error_count = 0
        
        # Latencies in seconds
        self.routing_latencies: List[float] = []
        self.routing_latency_sum = 0.0
        self.routing_latency_count = 0
        
        # Latency histogram buckets (in seconds)
        self.latency_buckets = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        self.bucket_counts = {b: 0 for b in self.latency_buckets}

        # Gauges
        self.active_websockets = 0
        self.live_vehicles_count = 0
        self.loaded_stops_count = 0
        self.loaded_routes_count = 0

    def record_request(self, method: str, endpoint: str, status_code: int):
        key = f'{method}:{endpoint}:{status_code}'
        with self._lock:
            self.request_counts[key] = self.request_counts.get(key, 0) + 1

    def record_routing_query(self, status: str, duration_sec: float):
        with self._lock:
            if status == "success":
                self.routing_success_count += 1
            elif status == "not_found":
                self.routing_not_found_count += 1
            else:
                self.routing_error_count += 1

            self.routing_latency_sum += duration_sec
            self.routing_latency_count += 1
            if len(self.routing_latencies) < 2000:
                self.routing_latencies.append(duration_sec)
            else:
                self.routing_latencies.pop(0)
                self.routing_latencies.append(duration_sec)

            for b in self.latency_buckets:
                if duration_sec <= b:
                    self.bucket_counts[b] += 1

    def set_active_websockets(self, count: int):
        with self._lock:
            self.active_websockets = max(0, count)

    def set_live_vehicles(self, count: int):
        with self._lock:
            self.live_vehicles_count = max(0, count)

    def set_gtfs_metadata(self, stops_count: int, routes_count: int):
        with self._lock:
            self.loaded_stops_count = stops_count
            self.loaded_routes_count = routes_count

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            uptime = time.time() - self.start_time
            avg_latency_ms = (
                (self.routing_latency_sum / self.routing_latency_count * 1000)
                if self.routing_latency_count > 0
                else 0.0
            )
            
            p50_ms = 0.0
            p95_ms = 0.0
            p99_ms = 0.0
            if self.routing_latencies:
                sorted_l = sorted(self.routing_latencies)
                n = len(sorted_l)
                p50_ms = sorted_l[int(n * 0.50)] * 1000
                p95_ms = sorted_l[min(n - 1, int(n * 0.95))] * 1000
                p99_ms = sorted_l[min(n - 1, int(n * 0.99))] * 1000

            return {
                "uptime_seconds": round(uptime, 2),
                "total_routing_queries": self.routing_latency_count,
                "routing_success": self.routing_success_count,
                "routing_not_found": self.routing_not_found_count,
                "routing_errors": self.routing_error_count,
                "latency_ms": {
                    "avg": round(avg_latency_ms, 2),
                    "p50": round(p50_ms, 2),
                    "p95": round(p95_ms, 2),
                    "p99": round(p99_ms, 2),
                },
                "active_websockets": self.active_websockets,
                "live_vehicles": self.live_vehicles_count,
                "loaded_stops": self.loaded_stops_count,
                "loaded_routes": self.loaded_routes_count,
            }

    def generate_prometheus_text(self) -> str:
        """Render metrics into Prometheus text format (v0.0.4)."""
        lines = []
        with self._lock:
            uptime = time.time() - self.start_time

            # Uptime
            lines.append("# HELP transit_engine_uptime_seconds Process uptime in seconds.")
            lines.append("# TYPE transit_engine_uptime_seconds gauge")
            lines.append(f"transit_engine_uptime_seconds {uptime:.2f}")

            # Loaded Stops & Routes
            lines.append("# HELP transit_engine_gtfs_stops_loaded Number of GTFS stops loaded into memory.")
            lines.append("# TYPE transit_engine_gtfs_stops_loaded gauge")
            lines.append(f"transit_engine_gtfs_stops_loaded {self.loaded_stops_count}")

            lines.append("# HELP transit_engine_gtfs_routes_loaded Number of GTFS routes loaded into memory.")
            lines.append("# TYPE transit_engine_gtfs_routes_loaded gauge")
            lines.append(f"transit_engine_gtfs_routes_loaded {self.loaded_routes_count}")

            # Active WebSocket Connections
            lines.append("# HELP transit_engine_active_websockets Current number of active WebSocket clients.")
            lines.append("# TYPE transit_engine_active_websockets gauge")
            lines.append(f"transit_engine_active_websockets {self.active_websockets}")

            # Live fleet vehicles
            lines.append("# HELP transit_engine_live_vehicles Active simulated fleet vehicles.")
            lines.append("# TYPE transit_engine_live_vehicles gauge")
            lines.append(f"transit_engine_live_vehicles {self.live_vehicles_count}")

            # Routing Requests Total
            lines.append("# HELP transit_engine_routing_requests_total Total number of RAPTOR routing queries executed.")
            lines.append("# TYPE transit_engine_routing_requests_total counter")
            lines.append(f'transit_engine_routing_requests_total{{status="success"}} {self.routing_success_count}')
            lines.append(f'transit_engine_routing_requests_total{{status="not_found"}} {self.routing_not_found_count}')
            lines.append(f'transit_engine_routing_requests_total{{status="error"}} {self.routing_error_count}')

            # Routing Duration Histogram
            lines.append("# HELP transit_engine_routing_duration_seconds RAPTOR route planning execution duration in seconds.")
            lines.append("# TYPE transit_engine_routing_duration_seconds histogram")
            for b in self.latency_buckets:
                lines.append(f'transit_engine_routing_duration_seconds_bucket{{le="{b}"}} {self.bucket_counts[b]}')
            lines.append(f'transit_engine_routing_duration_seconds_bucket{{le="+Inf"}} {self.routing_latency_count}')
            lines.append(f"transit_engine_routing_duration_seconds_sum {self.routing_latency_sum:.6f}")
            lines.append(f"transit_engine_routing_duration_seconds_count {self.routing_latency_count}")

            # HTTP Requests Total
            if self.request_counts:
                lines.append("# HELP transit_engine_http_requests_total Total HTTP requests served.")
                lines.append("# TYPE transit_engine_http_requests_total counter")
                for key, count in self.request_counts.items():
                    method, ep, sc = key.split(":")
                    lines.append(f'transit_engine_http_requests_total{{method="{method}",endpoint="{ep}",status="{sc}"}} {count}')

        return "\n".join(lines) + "\n"


metrics = MetricsCollector()
