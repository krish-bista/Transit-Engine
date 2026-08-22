import os
import struct
import pandas as pd
from typing import List, Dict, Any, Optional

class GTFSDataManager:
    def __init__(self, raw_dir: Optional[str] = None, binary_dir: Optional[str] = None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.raw_dir = raw_dir or os.path.join(base_dir, "raw_gtfs")
        self.binary_dir = binary_dir or os.path.join(base_dir, "binary_gtfs")
        
        # In-memory storage
        self.stops: List[Dict[str, Any]] = []
        self.stop_by_id: Dict[int, Dict[str, Any]] = {}
        self.stop_by_raw_id: Dict[str, int] = {}
        self.routes: Dict[str, Dict[str, Any]] = {}
        self.shapes: Dict[str, List[List[float]]] = {}
        self.trips: Dict[str, Dict[str, Any]] = {}
        self.stop_times: List[Dict[str, Any]] = []
        
        self.load_data()

    def load_data(self):
        # 1. Load stops.txt
        stops_file = os.path.join(self.raw_dir, "stops.txt")
        if not os.path.exists(stops_file):
            stops_file = os.path.join(self.raw_dir, "extracted", "stops.txt")

        if os.path.exists(stops_file):
            df_stops = pd.read_csv(stops_file, dtype=str)
            # Ensure deterministic 0-based indexing matching gtfs_compiler.py
            unique_stops = sorted(df_stops["stop_id"].unique(), key=str)
            self.stop_by_raw_id = {sid: idx for idx, sid in enumerate(unique_stops)}
            
            # Map stop_id -> details
            stops_dict = df_stops.drop_duplicates(subset=["stop_id"]).set_index("stop_id").to_dict(orient="index")
            
            for sid, idx in self.stop_by_raw_id.items():
                row = stops_dict.get(sid, {})
                stop_obj = {
                    "id": idx,
                    "raw_id": sid,
                    "name": row.get("stop_name", f"Stop {sid}"),
                    "lat": float(row.get("stop_lat", 0.0)),
                    "lon": float(row.get("stop_lon", 0.0)),
                }
                self.stops.append(stop_obj)
                self.stop_by_id[idx] = stop_obj

        # 2. Load routes.txt
        routes_file = os.path.join(self.raw_dir, "routes.txt")
        if not os.path.exists(routes_file):
            routes_file = os.path.join(self.raw_dir, "extracted", "routes.txt")

        if os.path.exists(routes_file):
            df_routes = pd.read_csv(routes_file, dtype=str)
            for _, r in df_routes.iterrows():
                rid = str(r.get("route_id", ""))
                color = str(r.get("route_color", "2563EB")).strip()
                if not color or color == "nan":
                    color = "2563EB"
                if not color.startswith("#"):
                    color = f"#{color}"
                self.routes[rid] = {
                    "id": rid,
                    "short_name": str(r.get("route_short_name", rid)),
                    "long_name": str(r.get("route_long_name", "")),
                    "color": color,
                    "text_color": "#" + str(r.get("route_text_color", "FFFFFF")).strip("#"),
                }

        # 3. Load shapes.txt
        shapes_file = os.path.join(self.raw_dir, "shapes.txt")
        if not os.path.exists(shapes_file):
            shapes_file = os.path.join(self.raw_dir, "extracted", "shapes.txt")

        if os.path.exists(shapes_file):
            df_shapes = pd.read_csv(shapes_file)
            df_shapes["seq"] = df_shapes["shape_pt_sequence"].astype(int)
            for shape_id, group in df_shapes.groupby("shape_id"):
                pts = group.sort_values("seq")[["shape_pt_lat", "shape_pt_lon"]].values.tolist()
                self.shapes[str(shape_id)] = pts

        # 4. Load sample stop_times for departure boards
        st_file = os.path.join(self.raw_dir, "stop_times.txt")
        if not os.path.exists(st_file):
            st_file = os.path.join(self.raw_dir, "extracted", "stop_times.txt")

        if os.path.exists(st_file):
            # Load subset of stop times to keep memory fast
            df_st = pd.read_csv(st_file, dtype=str, nrows=50000)
            for _, row in df_st.iterrows():
                sid_str = str(row["stop_id"])
                if sid_str in self.stop_by_raw_id:
                    sid_int = self.stop_by_raw_id[sid_str]
                    arr_sec = self.hms_to_sec(row["arrival_time"])
                    dep_sec = self.hms_to_sec(row["departure_time"])
                    self.stop_times.append({
                        "trip_id": str(row["trip_id"]),
                        "stop_id": sid_int,
                        "arr_sec": arr_sec,
                        "dep_sec": dep_sec,
                        "seq": int(row["stop_sequence"])
                    })

    @staticmethod
    def hms_to_sec(hms_str: str) -> int:
        try:
            parts = [int(p) for p in str(hms_str).strip().split(":")]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2:
                return parts[0] * 3600 + parts[1] * 60
            return 0
        except Exception:
            return 0

    @staticmethod
    def sec_to_hms(sec: int) -> str:
        h = (sec // 3600) % 24
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}"

    def get_stop(self, stop_id: int) -> Optional[Dict[str, Any]]:
        return self.stop_by_id.get(stop_id)

    def get_all_stops(self) -> List[Dict[str, Any]]:
        return self.stops

    def get_routes(self) -> Dict[str, Dict[str, Any]]:
        return self.routes

    def get_upcoming_departures(self, stop_id: int, current_sec: int, limit: int = 10) -> List[Dict[str, Any]]:
        departures = []
        for st in self.stop_times:
            if st["stop_id"] == stop_id and st["dep_sec"] >= current_sec:
                departures.append({
                    "trip_id": st["trip_id"],
                    "departure_sec": st["dep_sec"],
                    "departure_time": self.sec_to_hms(st["dep_sec"]),
                    "delay_sec": 0,
                })
        departures.sort(key=lambda d: d["departure_sec"])
        return departures[:limit]
