import os
import struct
import math
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
            unique_stops = sorted(df_stops["stop_id"].unique(), key=str)
            self.stop_by_raw_id = {sid: idx for idx, sid in enumerate(unique_stops)}
            
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
                rid = str(r.get("route_id", "")).strip()
                color = str(r.get("route_color", "4F46E5")).strip()
                if not color or color == "nan":
                    color = "4F46E5"
                if not color.startswith("#"):
                    color = f"#{color}"
                self.routes[rid] = {
                    "id": rid,
                    "short_name": str(r.get("route_short_name", rid)).strip(),
                    "long_name": str(r.get("route_long_name", "")).strip(),
                    "color": color,
                    "text_color": "#" + str(r.get("route_text_color", "FFFFFF")).strip("#"),
                }

        # 3. Load trips.txt (contains headsign, route_id, shape_id)
        trips_file = os.path.join(self.raw_dir, "trips.txt")
        if not os.path.exists(trips_file):
            trips_file = os.path.join(self.raw_dir, "extracted", "trips.txt")

        if os.path.exists(trips_file):
            df_trips = pd.read_csv(trips_file, dtype=str)
            for _, tr in df_trips.iterrows():
                tid = str(tr.get("trip_id", "")).strip()
                rid = str(tr.get("route_id", "")).strip()
                headsign = str(tr.get("trip_headsign", "")).strip()
                shape_id = str(tr.get("shape_id", "")).strip()
                self.trips[tid] = {
                    "trip_id": tid,
                    "route_id": rid,
                    "headsign": headsign,
                    "shape_id": shape_id
                }

        # 4. Load shapes.txt
        shapes_file = os.path.join(self.raw_dir, "shapes.txt")
        if not os.path.exists(shapes_file):
            shapes_file = os.path.join(self.raw_dir, "extracted", "shapes.txt")

        if os.path.exists(shapes_file):
            df_shapes = pd.read_csv(shapes_file)
            df_shapes["seq"] = df_shapes["shape_pt_sequence"].astype(int)
            for shape_id, group in df_shapes.groupby("shape_id"):
                pts = group.sort_values("seq")[["shape_pt_lat", "shape_pt_lon"]].values.tolist()
                self.shapes[str(shape_id)] = pts

        # 5. Load all stop_times.txt
        st_file = os.path.join(self.raw_dir, "stop_times.txt")
        if not os.path.exists(st_file):
            st_file = os.path.join(self.raw_dir, "extracted", "stop_times.txt")

        if os.path.exists(st_file):
            df_st = pd.read_csv(st_file, dtype=str)
            for _, row in df_st.iterrows():
                sid_str = str(row["stop_id"])
                if sid_str in self.stop_by_raw_id:
                    sid_int = self.stop_by_raw_id[sid_str]
                    arr_sec = self.hms_to_sec(row["arrival_time"])
                    dep_sec = self.hms_to_sec(row["departure_time"])
                    seq_val = int(row.get("stop_sequence", 0))
                    self.stop_times.append({
                        "trip_id": str(row["trip_id"]).strip(),
                        "stop_id": sid_int,
                        "arr_sec": arr_sec,
                        "dep_sec": dep_sec,
                        "seq": seq_val,
                        "stop_sequence": seq_val
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
        return f"{h:02d}:{m:02d}"

    def get_stop(self, stop_id: int) -> Optional[Dict[str, Any]]:
        return self.stop_by_id.get(stop_id)

    def get_all_stops(self) -> List[Dict[str, Any]]:
        return self.stops

    def get_routes(self) -> Dict[str, Dict[str, Any]]:
        return self.routes

    def find_nearest_stop(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        if not self.stops:
            return None
        best_stop = None
        min_dist = float("inf")
        for stop in self.stops:
            dlat = math.radians(stop["lat"] - lat)
            dlon = math.radians(stop["lon"] - lon)
            a = math.sin(dlat / 2.0)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(stop["lat"])) * math.sin(dlon / 2.0)**2
            dist = 2.0 * 6371000.0 * math.asin(math.sqrt(a))
            if dist < min_dist:
                min_dist = dist
                best_stop = dict(stop)
                best_stop["distance_m"] = int(dist)
        return best_stop

    def get_upcoming_departures(self, stop_id: int, current_sec: int, limit: int = 10) -> List[Dict[str, Any]]:
        departures = []
        for st in self.stop_times:
            if st["stop_id"] == stop_id and st["dep_sec"] >= current_sec:
                tid = st["trip_id"]
                trip_meta = self.trips.get(tid, {})
                rid = trip_meta.get("route_id", "")
                route_meta = self.routes.get(rid, {})
                headsign = trip_meta.get("headsign", "")
                bus_name = f"Bus {rid}" + (f" ({headsign})" if headsign else "")
                departures.append({
                    "trip_id": tid,
                    "route_id": rid,
                    "bus_name": bus_name,
                    "headsign": headsign,
                    "route_color": route_meta.get("color", "#4F46E5"),
                    "departure_sec": st["dep_sec"],
                    "departure_time": self.sec_to_hms(st["dep_sec"]),
                    "delay_sec": 0,
                })
        departures.sort(key=lambda d: d["departure_sec"])
        return departures[:limit]
