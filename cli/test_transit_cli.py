import pytest
from gateway.gtfs_data import GTFSDataManager
from gateway.raptor_engine import RaptorEngine
from cli.transit_cli import (
    resolve_stop,
    format_itinerary_ascii,
    run_validate_command,
    build_parser,
)

def test_resolve_stop():
    dm = GTFSDataManager()
    if dm.stops:
        first_stop = dm.stops[0]
        # Test by numeric ID
        found = resolve_stop(str(first_stop["id"]), dm)
        assert found is not None
        assert found["id"] == first_stop["id"]

        # Test by name substring
        name_substr = first_stop["name"][:5]
        found_name = resolve_stop(name_substr, dm)
        assert found_name is not None

def test_resolve_stop_not_found():
    dm = GTFSDataManager()
    found = resolve_stop("NON_EXISTENT_SUPER_RANDOM_STOP_NAME_12345", dm)
    assert found is None

def test_format_itinerary_ascii():
    source = {"id": 1, "name": "Source Stop"}
    target = {"id": 2, "name": "Target Stop"}
    
    empty_output = format_itinerary_ascii([], source, target)
    assert "No valid path found" in empty_output

    mock_itinerary = [
        {
            "is_walking": True,
            "board_time_formatted": "08:00:00",
            "alight_time_formatted": "08:02:00",
            "duration_mins": 2,
            "distance_m": 100,
            "alight_stop_name": "Boarding Stop",
        },
        {
            "is_walking": False,
            "bus_name": "Route 1",
            "headsign": "City Center",
            "board_stop_name": "Boarding Stop",
            "alight_stop_name": "Target Stop",
            "board_time_formatted": "08:05:00",
            "alight_time_formatted": "08:20:00",
            "duration_mins": 15,
        }
    ]
    output = format_itinerary_ascii(mock_itinerary, source, target)
    assert "Start: Source Stop" in output
    assert "Destination Reached: Target Stop" in output
    assert "[WALK]" in output
    assert "[Route 1]" in output

def test_run_validate_command():
    dm = GTFSDataManager()
    res = run_validate_command(dm)
    assert res == 0

def test_cli_argument_parser():
    parser = build_parser()
    
    # Route args
    args_route = parser.parse_args(["route", "-o", "Waterfront", "-d", "College", "-t", "08:00:00"])
    assert args_route.command == "route"
    assert args_route.origin == "Waterfront"
    assert args_route.destination == "College"
    assert args_route.time == "08:00:00"

    # Stops args
    args_stops = parser.parse_args(["stops", "-q", "Memorial", "--limit", "5"])
    assert args_stops.command == "stops"
    assert args_stops.query == "Memorial"
    assert args_stops.limit == 5

    # Validate args
    args_val = parser.parse_args(["validate"])
    assert args_val.command == "validate"

    # Health args
    args_health = parser.parse_args(["health", "--url", "http://127.0.0.1:8000"])
    assert args_health.command == "health"
    assert args_health.url == "http://127.0.0.1:8000"
