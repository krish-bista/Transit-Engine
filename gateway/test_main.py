import pytest
from fastapi.testclient import TestClient
from gateway.main import app, data_manager, ConnectionManager, get_thunder_bay_time
from gateway.gtfs_data import GTFSDataManager

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "stops_count" in data
    assert "routes_count" in data
    assert "active_ws_clients" in data
    assert "live_vehicles_count" in data

def test_get_stops():
    response = client.get("/api/stops?limit=10")
    assert response.status_code == 200
    stops = response.json()
    assert isinstance(stops, list)
    assert len(stops) <= 10
    if stops:
        assert "id" in stops[0]
        assert "name" in stops[0]
        assert "lat" in stops[0]
        assert "lon" in stops[0]

def test_search_stops():
    response = client.get("/api/stops?q=Water")
    assert response.status_code == 200
    stops = response.json()
    assert isinstance(stops, list)

def test_get_stop_detail_valid():
    stops = data_manager.get_all_stops()
    if stops:
        first_id = stops[0]["id"]
        response = client.get(f"/api/stops/{first_id}")
        assert response.status_code == 200
        stop = response.json()
        assert stop["id"] == first_id

def test_get_stop_detail_not_found():
    response = client.get("/api/stops/999999999")
    assert response.status_code == 404

def test_get_stop_departures():
    stops = data_manager.get_all_stops()
    if stops:
        first_id = stops[0]["id"]
        response = client.get(f"/api/stops/{first_id}/departures?time_sec=36000")
        assert response.status_code == 200
        data = response.json()
        assert "departures" in data
        assert data["stop_id"] == first_id

def test_get_routes():
    response = client.get("/api/routes")
    assert response.status_code == 200
    routes = response.json()
    assert isinstance(routes, list)

def test_nearest_stop():
    response = client.get("/api/nearest-stop?lat=48.4284&lon=-89.2642")
    assert response.status_code == 200
    stop = response.json()
    assert "id" in stop
    assert "name" in stop

def test_route_planning_valid():
    stops = data_manager.get_all_stops()
    if len(stops) >= 2:
        source_id = stops[0]["id"]
        target_id = stops[1]["id"]
        payload = {
            "source_stop": source_id,
            "target_stop": target_id,
            "departure_time": "14:00:00",
            "num_options": 2
        }
        response = client.post("/api/route", json=payload)
        assert response.status_code == 200
        result = response.json()
        assert "success" in result

def test_route_planning_invalid_stops():
    payload = {
        "source_stop": 999999991,
        "target_stop": 999999992,
        "departure_time": "14:00:00"
    }
    response = client.post("/api/route", json=payload)
    assert response.status_code == 400

def test_static_assets():
    res_manifest = client.get("/manifest.json")
    assert res_manifest.status_code == 200
    assert "name" in res_manifest.json()

    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200

    res_styles = client.get("/styles.css")
    assert res_styles.status_code == 200

    res_app = client.get("/app.js")
    assert res_app.status_code == 200

def test_time_conversion_utilities():
    assert GTFSDataManager.hms_to_sec("01:00:00") == 3600
    assert GTFSDataManager.hms_to_sec("00:30:00") == 1800
    assert GTFSDataManager.hms_to_sec("14:30:15") == 14 * 3600 + 30 * 60 + 15
    assert GTFSDataManager.hms_to_sec("invalid") == 0
    assert "1:00 AM" in GTFSDataManager.sec_to_hms(3600)
    assert "2:30 PM" in GTFSDataManager.sec_to_hms(14 * 3600 + 30 * 60)

def test_get_thunder_bay_time():
    t = get_thunder_bay_time()
    assert isinstance(t, int)
    assert 0 <= t < 86400

def test_connection_manager():
    manager = ConnectionManager()
    dummy_ws = "dummy_conn"
    manager.active_connections.append(dummy_ws)
    assert dummy_ws in manager.active_connections
    manager.disconnect(dummy_ws)
    assert dummy_ws not in manager.active_connections
    manager.disconnect("non_existent")

