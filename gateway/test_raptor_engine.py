import pytest
import math
from gateway.raptor_engine import RaptorEngine

@pytest.fixture
def sample_transit_network():
    """
    Creates a synthetic mini-network with 4 stops:
    Stop 0 (Thunder Bay North) -> Stop 1 (City Hall) -> Stop 2 (University)
    Route A connects 0 -> 1 -> 2 at 08:00 and 08:30.
    Stop 3 (Hospital) is within walking distance (<500m) of Stop 2.
    """
    stops = [
        {"id": 0, "name": "Stop 0 North", "lat": 48.4200, "lon": -89.2600},
        {"id": 1, "name": "Stop 1 Center", "lat": 48.4250, "lon": -89.2650},
        {"id": 2, "name": "Stop 2 Campus", "lat": 48.4300, "lon": -89.2700},
        {"id": 3, "name": "Stop 3 Hospital", "lat": 48.4305, "lon": -89.2705},  # Close to stop 2 (~60m)
    ]
    
    raw_stop_times = [
        # Trip 1 (Starts at 28800 = 08:00:00)
        {"trip_id": "T1", "stop_id": 0, "stop_sequence": 1, "arr_sec": 28800, "dep_sec": 28800},
        {"trip_id": "T1", "stop_id": 1, "stop_sequence": 2, "arr_sec": 29400, "dep_sec": 29460},
        {"trip_id": "T1", "stop_id": 2, "stop_sequence": 3, "arr_sec": 30000, "dep_sec": 30000},
        
        # Trip 2 (Starts at 30600 = 08:30:00)
        {"trip_id": "T2", "stop_id": 0, "stop_sequence": 1, "arr_sec": 30600, "dep_sec": 30600},
        {"trip_id": "T2", "stop_id": 1, "stop_sequence": 2, "arr_sec": 31200, "dep_sec": 31260},
        {"trip_id": "T2", "stop_id": 2, "stop_sequence": 3, "arr_sec": 31800, "dep_sec": 31800},
    ]
    
    routes_meta = {
        "1": {"route_id": "1", "route_short_name": "1", "route_long_name": "Crosstown"}
    }
    
    trips_meta = {
        "T1": {"trip_id": "T1", "route_id": "1", "headsign": "To Campus"},
        "T2": {"trip_id": "T2", "route_id": "1", "headsign": "To Campus"}
    }
    
    engine = RaptorEngine(stops, raw_stop_times, routes_meta, trips_meta)
    return engine

def test_haversine_distance(sample_transit_network):
    engine = sample_transit_network
    # Test identical point has 0 distance
    assert engine._haversine_meters(48.0, -89.0, 48.0, -89.0) == pytest.approx(0.0, abs=1e-5)
    
    # Test distance between two known coordinates
    dist = engine._haversine_meters(48.4200, -89.2600, 48.4250, -89.2650)
    assert 600 < dist < 800

def test_footpaths_generation(sample_transit_network):
    engine = sample_transit_network
    # Stop 2 and Stop 3 are very close (~60m apart)
    footpaths_from_2 = [fp[0] for fp in engine.footpaths.get(2, [])]
    assert 3 in footpaths_from_2
    
    footpaths_from_3 = [fp[0] for fp in engine.footpaths.get(3, [])]
    assert 2 in footpaths_from_3

def test_direct_route_planning(sample_transit_network):
    engine = sample_transit_network
    # Query route from Stop 0 to Stop 2 at 07:50:00 (28200)
    plan = engine.plan_route(source_stop=0, target_stop=2, departure_time=28200)
    assert plan is not None
    assert len(plan) == 1
    leg = plan[0]
    assert leg["board_stop"] == 0
    assert leg["alight_stop"] == 2
    assert leg["board_time"] == 28800
    assert leg["alight_time"] == 30000
    assert leg["real_route_id"] == "1"
    assert leg["headsign"] == "To Campus"
    assert leg["stops_count"] == 2

def test_route_with_walking_transfer(sample_transit_network):
    engine = sample_transit_network
    # Query route from Stop 0 to Stop 3 (requires bus 0->2 then walk 2->3)
    plan = engine.plan_route(source_stop=0, target_stop=3, departure_time=28200)
    assert plan is not None
    assert len(plan) == 2
    
    bus_leg = plan[0]
    walk_leg = plan[1]
    
    assert bus_leg["board_stop"] == 0
    assert bus_leg["alight_stop"] == 2
    assert walk_leg["board_stop"] == 2
    assert walk_leg["alight_stop"] == 3
    assert walk_leg["real_route_id"] == "WALK"

def test_route_planning_later_departure(sample_transit_network):
    engine = sample_transit_network
    # Departure at 08:15:00 (29700) should catch Trip 2 (08:30:00 = 30600)
    plan = engine.plan_route(source_stop=0, target_stop=2, departure_time=29700)
    assert plan is not None
    assert plan[0]["board_time"] == 30600
    assert plan[0]["alight_time"] == 31800

def test_invalid_routes(sample_transit_network):
    engine = sample_transit_network
    # Same source and target
    assert engine.plan_route(0, 0, 28000) is None
    
    # Out of bounds stop IDs
    assert engine.plan_route(0, 999, 28000) is None
    assert engine.plan_route(999, 1, 28000) is None
    
    # Missed all trips (e.g. 23:00 = 82800)
    assert engine.plan_route(0, 2, 82800) is None
