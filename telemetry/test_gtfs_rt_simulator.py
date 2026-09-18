import pytest
import math
from telemetry.gtfs_rt_simulator import (
    calculate_bearing,
    haversine_meters,
    interpolate_coordinate,
    GTFSRTSimulator,
)

def test_bearing_calculation():
    # Due North: (0,0) -> (1,0) should be 0 degrees
    b_north = calculate_bearing(0.0, 0.0, 1.0, 0.0)
    assert abs(b_north - 0.0) < 0.1

    # Due East: (0,0) -> (0,1) should be 90 degrees
    b_east = calculate_bearing(0.0, 0.0, 0.0, 1.0)
    assert abs(b_east - 90.0) < 0.1

    # Due South: (1,0) -> (0,0) should be 180 degrees
    b_south = calculate_bearing(1.0, 0.0, 0.0, 0.0)
    assert abs(b_south - 180.0) < 0.1

    # Due West: (0,1) -> (0,0) should be 270 degrees
    b_west = calculate_bearing(0.0, 1.0, 0.0, 0.0)
    assert abs(b_west - 270.0) < 0.1

def test_haversine_meters():
    # Distance between Thunder Bay coordinates
    dist = haversine_meters(48.4200, -89.2600, 48.4300, -89.2600)
    # 0.01 deg latitude is roughly 1111 meters
    assert 1000 < dist < 1200

def test_interpolate_coordinate():
    lat, lon = interpolate_coordinate(10.0, 20.0, 20.0, 40.0, 0.5)
    assert lat == 15.0
    assert lon == 30.0

    # Test clamping
    lat0, lon0 = interpolate_coordinate(10.0, 20.0, 20.0, 40.0, -0.5)
    assert lat0 == 10.0
    assert lon0 == 20.0

    lat1, lon1 = interpolate_coordinate(10.0, 20.0, 20.0, 40.0, 1.5)
    assert lat1 == 20.0
    assert lon1 == 40.0

def test_gtfs_rt_simulator_trip_interpolation():
    stops = {
        1: {"id": 1, "name": "Terminal A", "lat": 48.4000, "lon": -89.2500},
        2: {"id": 2, "name": "Midpoint Stop", "lat": 48.4100, "lon": -89.2500},
        3: {"id": 3, "name": "Terminal B", "lat": 48.4200, "lon": -89.2500},
    }
    stop_times = [
        {"trip_id": "T1", "stop_id": 1, "stop_sequence": 1, "arrival_time": 36000, "departure_time": 36000},
        {"trip_id": "T1", "stop_id": 2, "stop_sequence": 2, "arrival_time": 36600, "departure_time": 36600},
        {"trip_id": "T1", "stop_id": 3, "stop_sequence": 3, "arrival_time": 37200, "departure_time": 37200},
    ]
    trips = {"T1": {"trip_id": "T1", "route_id": "1", "trip_headsign": "Downtown"}}
    routes = {"1": {"route_id": "1", "route_short_name": "1", "route_long_name": "Mainline"}}

    sim = GTFSRTSimulator(stops, stop_times, trips, routes)
    sim.gps_noise_meters = 0.0  # Disable noise for deterministic testing

    # Before trip start
    assert sim.compute_vehicle_position_at_time("T1", 35000) is None

    # After trip end
    assert sim.compute_vehicle_position_at_time("T1", 38000) is None

    # Midpoint between stop 1 and stop 2 (at 36300, 50% between 36000 and 36600)
    pos = sim.compute_vehicle_position_at_time("T1", 36300)
    assert pos is not None
    assert pos["trip_id"] == "T1"
    assert pos["route_id"] == "1"
    assert pos["current_status"] == "IN_TRANSIT_TO"
    assert pos["current_stop_sequence"] == 1
    assert pos["next_stop_id"] == 2
    assert abs(pos["latitude"] - 48.4050) < 0.001
    assert abs(pos["longitude"] - -89.2500) < 0.001
    assert pos["speed_kmh"] > 0

def test_gtfs_rt_feed_generation():
    stops = {
        1: {"id": 1, "name": "Terminal A", "lat": 48.4000, "lon": -89.2500},
        2: {"id": 2, "name": "Terminal B", "lat": 48.4100, "lon": -89.2500},
    }
    stop_times = [
        {"trip_id": "T1", "stop_id": 1, "stop_sequence": 1, "arrival_time": 36000, "departure_time": 36000},
        {"trip_id": "T1", "stop_id": 2, "stop_sequence": 2, "arrival_time": 36600, "departure_time": 36600},
    ]
    trips = {"T1": {"trip_id": "T1", "route_id": "1", "trip_headsign": "Downtown"}}
    routes = {"1": {"route_id": "1", "route_short_name": "1"}}

    sim = GTFSRTSimulator(stops, stop_times, trips, routes)
    
    vp_feed = sim.build_gtfs_rt_vehicle_positions_feed(36300)
    assert "header" in vp_feed
    assert vp_feed["header"]["gtfs_realtime_version"] == "2.0"
    assert len(vp_feed["entity"]) == 1
    entity = vp_feed["entity"][0]
    assert "vehicle" in entity
    assert entity["vehicle"]["trip"]["trip_id"] == "T1"

    tu_feed = sim.build_gtfs_rt_trip_updates_feed(36300)
    assert "header" in tu_feed
    assert len(tu_feed["entity"]) == 1
    tu_entity = tu_feed["entity"][0]
    assert "trip_update" in tu_entity
    assert tu_entity["trip_update"]["trip"]["trip_id"] == "T1"
