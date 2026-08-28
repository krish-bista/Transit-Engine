from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw_gtfs"
BIN_DIR = ROOT / "binary_gtfs"

STOPS_CSV = RAW_DIR / "stops.txt"
ROUTES_CSV = RAW_DIR / "routes.txt"
TRIPS_CSV = RAW_DIR / "trips.txt"
STOP_TIMES_CSV = RAW_DIR / "stop_times.txt"

STOPS_BIN = BIN_DIR / "stops.bin"
STOP_TIMES_BIN = BIN_DIR / "stop_times.bin"


def build_id_map(series: pd.Series) -> dict[str, int]:
    unique = series.unique()
    return {str(v): i for i, v in enumerate(sorted(unique, key=str))}


def hms_to_seconds(hms: str) -> int:
    parts = str(hms).strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Bad time format: {hms!r}")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s


def main() -> None:
    t0 = time.perf_counter()
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading GTFS CSVs...")
    stops = pd.read_csv(STOPS_CSV, dtype=str)
    routes = pd.read_csv(ROUTES_CSV, dtype=str)
    trips = pd.read_csv(TRIPS_CSV, dtype=str)
    stop_times = pd.read_csv(STOP_TIMES_CSV, dtype=str)

    print(f"  stops:      {len(stops):>8,} rows")
    print(f"  routes:     {len(routes):>8,} rows")
    print(f"  trips:      {len(trips):>8,} rows")
    print(f"  stop_times: {len(stop_times):>8,} rows")

    print("Building ID maps...")
    stop_id_map = build_id_map(stops["stop_id"])
    route_id_map = build_id_map(routes["route_id"])
    trip_id_map = build_id_map(trips["trip_id"])

    print(f"  stop  IDs: {len(stop_id_map):>6,}  ->  0 ... {len(stop_id_map) - 1}")
    print(f"  route IDs: {len(route_id_map):>6,}  ->  0 ... {len(route_id_map) - 1}")
    print(f"  trip  IDs: {len(trip_id_map):>6,}  ->  0 ... {len(trip_id_map) - 1}")

    print("Packing stops.bin...")
    stop_fmt = "<Idd"
    with open(STOPS_BIN, "wb") as f:
        for _, row in stops.iterrows():
            sid = stop_id_map[str(row["stop_id"])]
            lat = float(row["stop_lat"])
            lon = float(row["stop_lon"])
            f.write(struct.pack(stop_fmt, sid, lat, lon))
    stop_bytes = STOPS_BIN.stat().st_size
    print(f"  -> {STOPS_BIN.name}: {len(stops):,} records, {stop_bytes:,} bytes")

    print("Packing stop_times.bin...")
    st_fmt = "<5I"
    written = 0
    skipped = 0
    with open(STOP_TIMES_BIN, "wb") as f:
        for _, row in stop_times.iterrows():
            raw_trip = str(row["trip_id"])
            raw_stop = str(row["stop_id"])

            if raw_trip not in trip_id_map or raw_stop not in stop_id_map:
                skipped += 1
                continue

            tid = trip_id_map[raw_trip]
            sid = stop_id_map[raw_stop]
            arr_sec = hms_to_seconds(row["arrival_time"])
            dep_sec = hms_to_seconds(row["departure_time"])
            seq = int(row["stop_sequence"])

            f.write(struct.pack(st_fmt, tid, sid, arr_sec, dep_sec, seq))
            written += 1

    st_bytes = STOP_TIMES_BIN.stat().st_size
    print(f"  -> {STOP_TIMES_BIN.name}: {written:,} records, {st_bytes:,} bytes")
    if skipped:
        print(f"  Skipped {skipped:,} rows (unresolved trip/stop IDs)")

    elapsed = time.perf_counter() - t0
    print(f"\nCompilation complete in {elapsed:.2f}s")
    print(f"  {STOPS_BIN}")
    print(f"  {STOP_TIMES_BIN}")


if __name__ == "__main__":
    sys.exit(main() or 0)
