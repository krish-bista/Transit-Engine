"""
GTFS Realtime (GTFS-RT) Telemetry & Delay Simulation Engine.
Simulates high-fidelity vehicle positions, kinematics, stop progress, and schedule delays.
"""

import math
import time
import random
from typing import Dict, List, Any, Optional, Tuple


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate forward azimuth bearing from (lat1, lon1) to (lat2, lon2) in degrees."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two GPS coordinates in meters."""
    r = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def interpolate_coordinate(lat1: float, lon1: float, lat2: float, lon2: float, fraction: float) -> Tuple[float, float]:
    """Linear geodesic interpolation between two points given a progress fraction [0.0, 1.0]."""
    clamped = max(0.0, min(1.0, fraction))
    lat = lat1 + (lat2 - lat1) * clamped
    lon = lon1 + (lon2 - lon1) * clamped
    return lat, lon


class GTFSRTSimulator:
    """
    High-fidelity GTFS Realtime Simulator.
    Generates dynamic vehicle telemetry and GTFS-RT feed structures.
    """

    def __init__(self, stops: Dict[int, Any], stop_times: List[Any], trips: Dict[str, Any], routes: Dict[str, Any]):
        self.stops = stops
        self.stop_times = stop_times
        self.trips = trips
        self.routes = routes
        
        # Index trips by trip_id
        self.trip_stoptimes_map: Dict[str, List[Any]] = {}
        for st in stop_times:
            tid = st.get("trip_id")
            if tid not in self.trip_stoptimes_map:
                self.trip_stoptimes_map[tid] = []
            self.trip_stoptimes_map[tid].append(st)

        # Sort each trip's stop times by stop_sequence
        for tid in self.trip_stoptimes_map:
            self.trip_stoptimes_map[tid].sort(key=lambda s: s.get("stop_sequence", 0))

        # Configurable delay parameters
        self.delay_variance_sec = 60
        self.gps_noise_meters = 2.0

    def compute_vehicle_position_at_time(
        self, trip_id: str, current_time_sec: int, delay_sec: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Compute interpolated vehicle position, speed, and heading for a trip at a given second of day.
        """
        st_list = self.trip_stoptimes_map.get(trip_id)
        if not st_list or len(st_list) < 2:
            return None

        trip_info = self.trips.get(trip_id, {})
        route_id = trip_info.get("route_id", "")
        headsign = trip_info.get("trip_headsign", "")

        adjusted_time = current_time_sec - delay_sec
        start_time = st_list[0].get("departure_time", 0)
        end_time = st_list[-1].get("arrival_time", 0)

        # If trip is not currently active
        if adjusted_time < start_time or adjusted_time > end_time:
            return None

        # Find the segment
        for i in range(len(st_list) - 1):
            s_curr = st_list[i]
            s_next = st_list[i + 1]

            t_dep = s_curr.get("departure_time", 0)
            t_arr = s_next.get("arrival_time", 0)

            if t_dep <= adjusted_time <= t_arr:
                stop1 = self.stops.get(s_curr.get("stop_id"))
                stop2 = self.stops.get(s_next.get("stop_id"))
                if not stop1 or not stop2:
                    continue

                duration = max(1, t_arr - t_dep)
                progress = (adjusted_time - t_dep) / duration
                lat, lon = interpolate_coordinate(
                    stop1["lat"], stop1["lon"], stop2["lat"], stop2["lon"], progress
                )

                # Add slight realistic GPS jitter
                if self.gps_noise_meters > 0:
                    jitter_lat = (random.random() - 0.5) * (self.gps_noise_meters / 111320.0)
                    jitter_lon = (random.random() - 0.5) * (self.gps_noise_meters / (111320.0 * math.cos(math.radians(lat))))
                    lat += jitter_lat
                    lon += jitter_lon

                bearing = calculate_bearing(stop1["lat"], stop1["lon"], stop2["lat"], stop2["lon"])
                segment_dist_m = haversine_meters(stop1["lat"], stop1["lon"], stop2["lat"], stop2["lon"])
                speed_mps = round(segment_dist_m / duration, 2)

                status = "IN_TRANSIT_TO" if progress > 0.05 else "STOPPED_AT"

                return {
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "vehicle_id": f"VEH_{route_id}_{trip_id[-4:] if len(trip_id) >= 4 else trip_id}",
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "bearing": round(bearing, 1),
                    "speed_mps": speed_mps,
                    "speed_kmh": round(speed_mps * 3.6, 1),
                    "current_stop_sequence": s_curr.get("stop_sequence", 0),
                    "current_status": status,
                    "next_stop_id": s_next.get("stop_id"),
                    "next_stop_name": stop2.get("name", ""),
                    "headsign": headsign,
                    "delay_seconds": delay_sec,
                    "timestamp": int(time.time()),
                }

        return None

    def generate_fleet_snapshot(self, current_time_sec: int) -> List[Dict[str, Any]]:
        """Generate positions for all currently active trips in the network."""
        vehicles = []
        for trip_id in self.trip_stoptimes_map:
            # Deterministic delay seed per trip to simulate realistic conditions
            random.seed(hash(trip_id) % 10000)
            trip_delay = int(random.gauss(30, self.delay_variance_sec))
            
            v = self.compute_vehicle_position_at_time(trip_id, current_time_sec, delay_sec=trip_delay)
            if v:
                vehicles.append(v)
        return vehicles

    def build_gtfs_rt_vehicle_positions_feed(self, current_time_sec: int) -> Dict[str, Any]:
        """Format vehicle positions as standard GTFS-RT JSON FeedMessage."""
        snapshot = self.generate_fleet_snapshot(current_time_sec)
        feed_entities = []

        for v in snapshot:
            entity = {
                "id": f"entity_vp_{v['vehicle_id']}",
                "vehicle": {
                    "trip": {
                        "trip_id": str(v["trip_id"]),
                        "route_id": str(v["route_id"]),
                    },
                    "position": {
                        "latitude": v["latitude"],
                        "longitude": v["longitude"],
                        "bearing": v["bearing"],
                        "speed": v["speed_mps"],
                    },
                    "current_stop_sequence": v["current_stop_sequence"],
                    "current_status": v["current_status"],
                    "timestamp": v["timestamp"],
                    "vehicle": {
                        "id": v["vehicle_id"],
                        "label": f"Bus {v['route_id']}",
                    },
                },
            }
            feed_entities.append(entity)

        return {
            "header": {
                "gtfs_realtime_version": "2.0",
                "incrementality": "FULL_DATASET",
                "timestamp": int(time.time()),
            },
            "entity": feed_entities,
        }

    def build_gtfs_rt_trip_updates_feed(self, current_time_sec: int) -> Dict[str, Any]:
        """Format schedule delays as standard GTFS-RT TripUpdate FeedMessage."""
        snapshot = self.generate_fleet_snapshot(current_time_sec)
        feed_entities = []

        for v in snapshot:
            tid = v["trip_id"]
            st_list = self.trip_stoptimes_map.get(tid, [])
            stop_updates = []

            for st in st_list:
                seq = st.get("stop_sequence", 0)
                if seq >= v["current_stop_sequence"]:
                    arr_time = st.get("arrival_time", 0) + v["delay_seconds"]
                    dep_time = st.get("departure_time", 0) + v["delay_seconds"]
                    stop_updates.append({
                        "stop_sequence": seq,
                        "stop_id": str(st.get("stop_id")),
                        "arrival": {
                            "delay": v["delay_seconds"],
                            "time": arr_time,
                        },
                        "departure": {
                            "delay": v["delay_seconds"],
                            "time": dep_time,
                        },
                    })

            entity = {
                "id": f"entity_tu_{v['vehicle_id']}",
                "trip_update": {
                    "trip": {
                        "trip_id": str(v["trip_id"]),
                        "route_id": str(v["route_id"]),
                    },
                    "vehicle": {
                        "id": v["vehicle_id"],
                    },
                    "stop_time_update": stop_updates,
                    "timestamp": v["timestamp"],
                    "delay": v["delay_seconds"],
                },
            }
            feed_entities.append(entity)

        return {
            "header": {
                "gtfs_realtime_version": "2.0",
                "incrementality": "FULL_DATASET",
                "timestamp": int(time.time()),
            },
            "entity": feed_entities,
        }
