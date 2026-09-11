import pytest
from fastapi.testclient import TestClient
from gateway.main import app, data_manager

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "stops_count" in data
    assert "routes_count" in data

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
