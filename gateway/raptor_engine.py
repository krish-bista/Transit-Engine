import math
from typing import List, Dict, Any, Optional, Tuple

class RaptorEngine:
    def __init__(self, stops: List[Dict[str, Any]], raw_stop_times: List[Dict[str, Any]], routes_meta: Dict[str, Any]):
        self.stops = stops
        self.num_stops = len(stops)
        self.routes_meta = routes_meta
        self.stop_by_id = {s["id"]: s for s in stops}

        # Build Routes & Index
        self._build_index(raw_stop_times)
        self._build_footpaths()

    def _haversine_meters(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371000.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2.0)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0)**2
        return 2.0 * R * math.asin(math.sqrt(a))

    def _build_footpaths(self):
        self.footpaths: Dict[int, List[Tuple[int, int, int]]] = {i: [] for i in range(self.num_stops)}
        max_dist = 500.0
        walk_speed = 1.25 # m/s

        for i in range(self.num_stops):
            s1 = self.stops[i]
            for j in range(self.num_stops):
                if i == j:
                    continue
                s2 = self.stops[j]
                # Quick bounding box filter (~500m is ~0.005 deg)
                if abs(s1["lat"] - s2["lat"]) > 0.006 or abs(s1["lon"] - s2["lon"]) > 0.009:
                    continue
                dist = self._haversine_meters(s1["lat"], s1["lon"], s2["lat"], s2["lon"])
                if dist <= max_dist:
                    dur_sec = max(30, int(dist / walk_speed))
                    self.footpaths[i].append((j, dur_sec, int(dist)))

    def _build_index(self, raw_stop_times: List[Dict[str, Any]]):
        # 1. Group by trip
        trips_st: Dict[str, List[Dict[str, Any]]] = {}
        for st in raw_stop_times:
            tid = st["trip_id"]
            if tid not in trips_st:
                trips_st[tid] = []
            trips_st[tid].append(st)

        # Sort each trip by stop_sequence
        for tid in trips_st:
            trips_st[tid].sort(key=lambda x: x["stop_sequence"])

        # 2. Group by unique stop sequence -> Route
        seq_to_trips: Dict[Tuple[int, ...], List[List[Dict[str, Any]]]] = {}
        for tid, st_list in trips_st.items():
            seq = tuple(st["stop_id"] for st in st_list)
            if seq not in seq_to_trips:
                seq_to_trips[seq] = []
            seq_to_trips[seq].append(st_list)

        self.routes = []
        self.stop_to_routes: Dict[int, List[int]] = {i: [] for i in range(self.num_stops)}

        for route_id, (seq, trips) in enumerate(seq_to_trips.items()):
            # Sort trips within route by departure time at first stop
            trips.sort(key=lambda st_list: st_list[0]["dep_sec"])

            route_obj = {
                "id": route_id,
                "stops": list(seq),
                "trips": trips, # list of stop_time lists
                "num_stops": len(seq),
                "num_trips": len(trips)
            }
            self.routes.append(route_obj)

            for stop_id in seq:
                if stop_id < self.num_stops:
                    if not self.stop_to_routes[stop_id] or self.stop_to_routes[stop_id][-1] != route_id:
                        self.stop_to_routes[stop_id].append(route_id)

    def plan_route(self, source_stop: int, target_stop: int, departure_time: int) -> Optional[List[Dict[str, Any]]]:
        if source_stop == target_stop or source_stop >= self.num_stops or target_stop >= self.num_stops:
            return None

        INF = 10**9
        earliest_arrival = [INF] * self.num_stops
        parent_stop = [None] * self.num_stops
        parent_route = [None] * self.num_stops
        board_time = [0] * self.num_stops
        alight_time = [0] * self.num_stops

        earliest_arrival[source_stop] = departure_time
        marked_stops = {source_stop}

        # Initial walking footpaths from source
        for to_stop, dur, dist in self.footpaths.get(source_stop, []):
            walk_arr = departure_time + dur
            if walk_arr < earliest_arrival[to_stop]:
                earliest_arrival[to_stop] = walk_arr
                marked_stops.add(to_stop)
                parent_stop[to_stop] = source_stop
                parent_route[to_stop] = "WALK"
                board_time[to_stop] = departure_time
                alight_time[to_stop] = walk_arr

        # RAPTOR rounds (up to 4 transfers)
        for k in range(4):
            prev_arrival = list(earliest_arrival)
            next_marked = set()
            route_boarding = {}

            # Step 1: Accumulate routes serving marked stops
            for s in marked_stops:
                for r_id in self.stop_to_routes.get(s, []):
                    route = self.routes[r_id]
                    try:
                        p = route["stops"].index(s)
                        if r_id not in route_boarding or p < route_boarding[r_id]:
                            route_boarding[r_id] = p
                    except ValueError:
                        pass

            # Step 2: Traverse each route
            for r_id, p_start in route_boarding.items():
                route = self.routes[r_id]
                current_trip_idx = None
                board_stop_id = None
                current_board_time = 0

                for p in range(p_start, route["num_stops"]):
                    s_id = route["stops"][p]

                    # Alight check
                    if current_trip_idx is not None:
                        st = route["trips"][current_trip_idx][p]
                        if st["arr_sec"] < earliest_arrival[s_id]:
                            earliest_arrival[s_id] = st["arr_sec"]
                            next_marked.add(s_id)
                            parent_stop[s_id] = board_stop_id
                            parent_route[s_id] = r_id
                            board_time[s_id] = current_board_time
                            alight_time[s_id] = st["arr_sec"]

                    # Boarding check
                    if s_id in marked_stops and prev_arrival[s_id] != INF:
                        # Binary search earliest trip with dep_sec >= prev_arrival[s_id]
                        trips = route["trips"]
                        low = 0
                        high = (current_trip_idx if current_trip_idx is not None else len(trips)) - 1
                        best_t = None

                        while low <= high:
                            mid = (low + high) // 2
                            if trips[mid][p]["dep_sec"] >= prev_arrival[s_id]:
                                best_t = mid
                                high = mid - 1
                            else:
                                low = mid + 1

                        if best_t is not None:
                            current_trip_idx = best_t
                            board_stop_id = s_id
                            current_board_time = trips[best_t][p]["dep_sec"]

            # Step 3: Footpath relaxation (NO chained footpaths)
            bus_alighted = [s for s in next_marked if parent_route[s] != "WALK"]
            for u in bus_alighted:
                for to_stop, dur, dist in self.footpaths.get(u, []):
                    walk_arr = earliest_arrival[u] + dur
                    if walk_arr < earliest_arrival[to_stop]:
                        earliest_arrival[to_stop] = walk_arr
                        next_marked.add(to_stop)
                        parent_stop[to_stop] = u
                        parent_route[to_stop] = "WALK"
                        board_time[to_stop] = earliest_arrival[u]
                        alight_time[to_stop] = walk_arr

            if not next_marked:
                break
            marked_stops = next_marked

        # Reconstruct path
        if earliest_arrival[target_stop] == INF:
            return None

        path = []
        curr = target_stop
        visited = set()

        while curr != source_stop and parent_stop[curr] is not None and curr not in visited:
            visited.add(curr)
            b_id = parent_stop[curr]
            r_id = parent_route[curr]

            path.append({
                "board_stop": b_id,
                "alight_stop": curr,
                "route_id": r_id,
                "board_time": board_time[curr],
                "alight_time": alight_time[curr]
            })
            curr = b_id

        path.reverse()
        return path
