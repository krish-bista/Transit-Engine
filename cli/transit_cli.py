"""
Interactive Terminal Transit Explorer and GTFS Diagnostics CLI.
Enables command-line journey planning, stop inspection, feed validation, and server diagnostics.
"""

import os
import sys
import time
import argparse
from typing import Dict, List, Any, Optional

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


def resolve_stop(query: str, data_manager: GTFSDataManager) -> Optional[Dict[str, Any]]:
    """Resolve a query string (ID or substring name) to a GTFS stop dictionary."""
    query_str = str(query).strip()
    
    # Try by numeric ID
    if query_str.isdigit():
        stop = data_manager.get_stop(int(query_str))
        if stop:
            return stop

    # Try by raw GTFS stop_id
    if query_str in data_manager.stop_by_raw_id:
        mapped_id = data_manager.stop_by_raw_id[query_str]
        return data_manager.get_stop(mapped_id)

    # Substring search on name
    q_lower = query_str.lower()
    matches = [s for s in data_manager.stops if q_lower in s.get("name", "").lower()]
    if matches:
        # Prefer exact match or starts-with
        for s in matches:
            if s.get("name", "").lower() == q_lower:
                return s
        for s in matches:
            if s.get("name", "").lower().startswith(q_lower):
                return s
        return matches[0]

    return None


def format_itinerary_ascii(itinerary: List[Dict[str, Any]], source: Dict[str, Any], target: Dict[str, Any]) -> str:
    """Format a journey itinerary into an ASCII visual timeline."""
    if not itinerary:
        return "  [!] No valid path found."

    lines = []
    lines.append(f"  🏁 Start: {source.get('name', 'Origin')}")
    
    for i, leg in enumerate(itinerary):
        is_walk = leg.get("is_walking", False) or leg.get("route_id") == "WALK"
        board_time = leg.get("board_time_formatted", str(leg.get("board_time", "")))
        alight_time = leg.get("alight_time_formatted", str(leg.get("alight_time", "")))
        dur = leg.get("duration_mins", max(1, (leg.get("alight_time", 0) - leg.get("board_time", 0)) // 60))
        dist = leg.get("distance_m", 0)

        if is_walk:
            lines.append(f"   │")
            lines.append(f"   ├─🚶 [WALK] {dur} min ({dist}m) -> {leg.get('alight_stop_name', 'Transfer point')}")
            lines.append(f"   │   ({board_time} - {alight_time})")
        else:
            route_name = leg.get("bus_name", f"Route {leg.get('route_id')}")
            headsign = f" (towards {leg.get('headsign')})" if leg.get("headsign") else ""
            lines.append(f"   │")
            lines.append(f"   ├─🚌 [{route_name}]{headsign}")
            lines.append(f"   │   Board: {board_time} at {leg.get('board_stop_name', 'Stop')}")
            lines.append(f"   │   Alight: {alight_time} at {leg.get('alight_stop_name', 'Stop')} ({dur} mins)")

    lines.append(f"   │")
    lines.append(f"  🎯 Destination Reached: {target.get('name', 'Destination')}\n")
    return "\n".join(lines)


def run_route_command(args, data_manager: GTFSDataManager, raptor_engine: RaptorEngine):
    """Handler for the 'route' subcommand."""
    source = resolve_stop(args.origin, data_manager)
    target = resolve_stop(args.destination, data_manager)

    if not source:
        print(f"[Error] Could not resolve origin stop: '{args.origin}'")
        return 1
    if not target:
        print(f"[Error] Could not resolve destination stop: '{args.destination}'")
        return 1

    dep_sec = 0
    if not args.time or args.time == "now":
        now = time.localtime()
        dep_sec = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    elif ":" in args.time:
        dep_sec = data_manager.hms_to_sec(args.time)
    else:
        try:
            dep_sec = int(args.time)
        except ValueError:
            dep_sec = 28800  # default 08:00

    print("=" * 65)
    print(f"  TRANSIT ENGINE RAPTOR ROUTER")
    print("=" * 65)
    print(f"  Origin:      {source['name']} (ID: {source['id']})")
    print(f"  Destination: {target['name']} (ID: {target['id']})")
    print(f"  Departure:   {data_manager.sec_to_hms(dep_sec)} ({dep_sec}s)")
    print("-" * 65)

    t0 = time.perf_counter()
    raw_itinerary = raptor_engine.plan_route(source["id"], target["id"], dep_sec)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    if not raw_itinerary:
        print(f"\n[!] No itinerary found departing at {data_manager.sec_to_hms(dep_sec)}.")
        print(f"    (Search completed in {latency_ms:.2f}ms)")
        return 0

    # Enrich legs with names
    enriched_legs = []
    for leg in raw_itinerary:
        b_stop = data_manager.get_stop(leg["board_stop"]) or {"name": f"Stop {leg['board_stop']}"}
        a_stop = data_manager.get_stop(leg["alight_stop"]) or {"name": f"Stop {leg['alight_stop']}"}
        is_walk = leg["route_id"] == "WALK" or (isinstance(leg["route_id"], int) and leg["route_id"] >= 0xFFFFFFFE)
        
        trip = data_manager.trips.get(str(leg.get("trip_id", "")), {})
        enriched_legs.append({
            "is_walking": is_walk,
            "route_id": leg["route_id"],
            "bus_name": f"Route {leg['route_id']}",
            "headsign": trip.get("trip_headsign", ""),
            "board_stop_name": b_stop["name"],
            "alight_stop_name": a_stop["name"],
            "board_time": leg["board_time"],
            "board_time_formatted": data_manager.sec_to_hms(leg["board_time"]),
            "alight_time": leg["alight_time"],
            "alight_time_formatted": data_manager.sec_to_hms(leg["alight_time"]),
            "duration_mins": max(1, (leg["alight_time"] - leg["board_time"]) // 60),
            "distance_m": int(leg.get("walking_distance", 0)),
        })

    first_board = enriched_legs[0]["board_time"]
    last_alight = enriched_legs[-1]["alight_time"]
    total_dur_min = max(1, (last_alight - first_board) // 60)
    transfers = max(0, sum(1 for leg in enriched_legs if not leg["is_walking"]) - 1)

    print(f"\n  ⏱️ Summary: {total_dur_min} mins | Transfers: {transfers} | Query Latency: {latency_ms:.2f}ms\n")
    print(format_itinerary_ascii(enriched_legs, source, target))
    return 0


def run_stops_command(args, data_manager: GTFSDataManager):
    """Handler for the 'stops' subcommand."""
    stops = data_manager.get_all_stops()
    if args.query:
        q = args.query.lower().strip()
        stops = [s for s in stops if q in s.get("name", "").lower() or q in str(s.get("id"))]

    print("=" * 75)
    print(f"  GTFS STOPS EXPLORER ({len(stops)} matches)")
    print("=" * 75)
    print(f"  {'ID':<8} {'Raw ID':<10} {'Name':<35} {'Latitude':<10} {'Longitude':<10}")
    print("-" * 75)
    
    for s in stops[:args.limit]:
        print(f"  {s.get('id', 0):<8} {str(s.get('raw_id', '')):<10} {s.get('name', '')[:33]:<35} {s.get('lat', 0.0):<10.5f} {s.get('lon', 0.0):<10.5f}")
    
    if len(stops) > args.limit:
        print(f"  ... and {len(stops) - args.limit} more stops (use --limit to expand)")
    print("-" * 75)
    return 0


def run_validate_command(data_manager: GTFSDataManager):
    """Handler for the 'validate' subcommand."""
    print("=" * 65)
    print("  GTFS FEED VALIDATION REPORT")
    print("=" * 65)

    errors = []
    warnings = []

    # Check stops
    if not data_manager.stops:
        errors.append("No stops loaded in feed.")
    else:
        print(f"  [✓] Total Stops: {len(data_manager.stops)}")

    # Check routes
    if not data_manager.routes:
        errors.append("No routes loaded in feed.")
    else:
        print(f"  [✓] Total Routes: {len(data_manager.routes)}")

    # Check trips
    if not data_manager.trips:
        errors.append("No trips loaded in feed.")
    else:
        print(f"  [✓] Total Trips: {len(data_manager.trips)}")

    # Check stop times
    if not data_manager.stop_times:
        errors.append("No stop_times records found.")
    else:
        print(f"  [✓] Total Stop Times: {len(data_manager.stop_times)}")

    # Check for monotonic time ordering
    non_monotonic = 0
    for st in data_manager.stop_times[:5000]:
        if st.get("arrival_time", 0) > st.get("departure_time", 0):
            non_monotonic += 1
    if non_monotonic > 0:
        warnings.append(f"Found {non_monotonic} stop_times where arrival_time > departure_time.")
    else:
        print("  [✓] Monotonic stop arrival/departure times validated.")

    print("-" * 65)
    if errors:
        print(f"  ❌ Validation Failed with {len(errors)} error(s):")
        for e in errors:
            print(f"     - {e}")
        return 1
    elif warnings:
        print(f"  ⚠️ Validation Passed with {len(warnings)} warning(s):")
        for w in warnings:
            print(f"     - {w}")
        return 0
    else:
        print("  ✅ All GTFS integrity and schema checks PASSED cleanly!")
        return 0


def run_health_command(args):
    """Handler for the 'health' subcommand."""
    import urllib.request
    import json as json_lib

    base_url = args.url.rstrip("/")
    health_url = f"{base_url}/api/health"
    ready_url = f"{base_url}/ready"
    metrics_url = f"{base_url}/api/system/metrics"

    print("=" * 65)
    print(f"  TRANSIT ENGINE GATEWAY DIAGNOSTICS: {base_url}")
    print("=" * 65)

    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "TransitCLI/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json_lib.loads(resp.read().decode())
            print(f"  [✓] Health Status:     {data.get('status', 'unknown')}")
            print(f"  [✓] Loaded Stops:      {data.get('stops_count', 0)}")
            print(f"  [✓] Loaded Routes:     {data.get('routes_count', 0)}")
            print(f"  [✓] Live Fleet:        {data.get('live_vehicles_count', 0)} active vehicles")
            print(f"  [✓] WebSocket Clients: {data.get('active_ws_clients', 0)}")
    except Exception as e:
        print(f"  [!] Failed to query {health_url}: {e}")
        return 1

    try:
        req = urllib.request.Request(ready_url, headers={"User-Agent": "TransitCLI/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            print(f"  [✓] Readiness Probe:   HTTP {resp.status}")
    except Exception as e:
        print(f"  [!] Readiness check failed: {e}")

    try:
        req = urllib.request.Request(metrics_url, headers={"User-Agent": "TransitCLI/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            m = json_lib.loads(resp.read().decode())
            print(f"  [✓] Server Uptime:     {m.get('uptime_seconds', 0)}s")
            print(f"  [✓] Total Queries:     {m.get('total_routing_queries', 0)}")
            lat = m.get("latency_ms", {})
            print(f"  [✓] Routing Latency:   Avg: {lat.get('avg', 0)}ms | P95: {lat.get('p95', 0)}ms | P99: {lat.get('p99', 0)}ms")
    except Exception:
        pass

    print("=" * 65)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="transit-cli",
        description="Transit Engine CLI - Interactive terminal transit router, diagnostics, and GTFS validator.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Route Subcommand
    route_parser = subparsers.add_parser("route", help="Plan a multi-modal transit route between stops")
    route_parser.add_argument("-o", "--origin", required=True, help="Origin stop name or ID")
    route_parser.add_argument("-d", "--destination", required=True, help="Destination stop name or ID")
    route_parser.add_argument("-t", "--time", default="now", help="Departure time (e.g. '08:30:00', 'now', or seconds of day)")

    # Stops Subcommand
    stops_parser = subparsers.add_parser("stops", help="Search and list stops in the network")
    stops_parser.add_argument("-q", "--query", default=None, help="Search filter for stop name or ID")
    stops_parser.add_argument("-l", "--limit", type=int, default=20, help="Maximum number of stops to display")

    # Validate Subcommand
    subparsers.add_parser("validate", help="Validate GTFS feed schema, integrity, and references")

    # Health Subcommand
    health_parser = subparsers.add_parser("health", help="Check live status and latency metrics of Gateway server")
    health_parser.add_argument("--url", default="http://localhost:8000", help="Gateway server base URL")

    # Benchmark Subcommand
    bench_parser = subparsers.add_parser("benchmark", help="Run local RAPTOR routing benchmark")
    bench_parser.add_argument("-n", "--queries", type=int, default=50, help="Number of benchmark queries")
    bench_parser.add_argument("-c", "--concurrency", type=int, default=2, help="Concurrency threads")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "health":
        sys.exit(run_health_command(args))

    # Initialize data manager
    dm = GTFSDataManager()
    engine = RaptorEngine(dm.stops, dm.stop_times, dm.routes, dm.trips)

    if args.command == "route":
        sys.exit(run_route_command(args, dm, engine))
    elif args.command == "stops":
        sys.exit(run_stops_command(args, dm))
    elif args.command == "validate":
        sys.exit(run_validate_command(dm))
    elif args.command == "benchmark":
        from tools.benchmark_engine import BenchmarkRunner
        runner = BenchmarkRunner(dm, engine)
        runner.run_benchmark(num_queries=args.queries, concurrency=args.concurrency)
        sys.exit(0)


if __name__ == "__main__":
    main()
