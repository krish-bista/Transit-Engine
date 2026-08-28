from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
STOPS_CSV = ROOT / "raw_gtfs" / "stops.txt"
OUTPUT = ROOT / "client_android" / "app" / "src" / "main" / "assets" / "stops.json"


def main() -> None:
    print(f"Reading {STOPS_CSV} ...")
    stops = pd.read_csv(STOPS_CSV, dtype=str)

    unique_ids = sorted(stops["stop_id"].unique(), key=str)
    id_map = {sid: i for i, sid in enumerate(unique_ids)}
    name_lookup = dict(zip(stops["stop_id"], stops["stop_name"]))

    result = []
    for sid in unique_ids:
        result.append({
            "id": id_map[sid],
            "name": name_lookup[sid],
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing {len(result)} stops to {OUTPUT} ...")
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    for entry in result[:5]:
        print(f"  {entry['id']:>4}: {entry['name']}")
    print(f"  ... ({len(result)} total)")
    print("Done.")


if __name__ == "__main__":
    sys.exit(main() or 0)
