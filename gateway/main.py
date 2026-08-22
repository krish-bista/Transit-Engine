import os
import time
import json
import math
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gtfs_data import GTFSDataManager, THUNDER_BAY_ROUTES
from raptor_engine import RaptorEngine

app = FastAPI(
    title="City Transit Guide API",
    description="Real-Time Passenger Transit Router with Step-by-Step Directions and Live Bus Tracking.",
    version="2.1.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data & Routing Engines
data_manager = GTFSDataManager()
raptor_engine = RaptorEngine(data_manager.stops, data_manager.stop_times, data_manager.routes, data_manager.trips)

# WebSocket client manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Real-time state
live_delays: Dict[int, Dict[str, Any]] = {}
live_vehicles: List[Dict[str, Any]] = []

# Pydantic Schemas
class RoutePlanRequest(BaseModel):
    source_stop: int
    target_stop: int
    departure_time: Optional[Any] = None
    departure_date: Optional[str] = "today"
    num_options: Optional[int] = 3

class StopDTO(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    raw_id: str

# Static Files
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/", include_in_schema=False)
def serve_root():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"system": "Transit Guide", "version": "2.1.0", "status": "online"}

@app.get("/styles.css", include_in_schema=False)
def serve_styles():
    return FileResponse(os.path.join(WEB_DIR, "styles.css"))

@app.get("/app.js", include_in_schema=False)
def serve_app_js():
    return FileResponse(os.path.join(WEB_DIR, "app.js"))

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "stops_count": len(data_manager.stops),
        "routes_count": len(raptor_engine.routes),
        "walking_footpaths": sum(len(fps) for fps in raptor_engine.footpaths.values()),
        "active_ws_clients": len(ws_manager.active_connections),
        "live_vehicles_count": len(live_vehicles)
    }

@app.get("/api/nearest-stop")
def get_nearest_stop(lat: float, lon: float):
    stop = data_manager.find_nearest_stop(lat, lon)
    if not stop:
        raise HTTPException(status_code=404, detail="No nearby transit stop found")
    return stop

@app.get("/api/stops", response_model=List[StopDTO])
def get_stops(q: Optional[str] = None, limit: int = 1000):
    stops = data_manager.get_all_stops()
    if q:
        query_lower = q.lower().strip()
        filtered = [s for s in stops if query_lower in s["name"].lower() or query_lower in str(s["id"])]
        return filtered[:limit]
    return stops[:limit]

@app.get("/api/stops/{stop_id}")
def get_stop_detail(stop_id: int):
    stop = data_manager.get_stop(stop_id)
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found")
    return stop

@app.get("/api/routes")
def get_routes():
    return list(data_manager.get_routes().values())

@app.get("/api/stops/{stop_id}/departures")
def get_stop_departures(stop_id: int, time_sec: Optional[int] = None):
    if time_sec is None:
        time_sec = 31620
    departures = data_manager.get_upcoming_departures(stop_id, time_sec)
    for dep in departures:
        tid = dep["trip_id"]
        if tid in live_delays:
            dep["delay_sec"] = live_delays[tid].get("delay", 0)
    return {
        "stop_id": stop_id,
        "current_time": data_manager.sec_to_hms(time_sec),
        "departures": departures
    }

def find_live_vehicle_for_route(bus_number: str, board_stop: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    target_v = None
    for v in live_vehicles:
        if str(v.get("route_id", "")).strip().lower() == bus_number.strip().lower():
            target_v = v
            break
    if not target_v and live_vehicles:
        target_v = live_vehicles[0]

    if not target_v or not board_stop:
        return None

    d_lat = (target_v["lat"] - board_stop["lat"]) * 111320
    d_lon = (target_v["lon"] - board_stop["lon"]) * 111320 * math.cos(math.radians(board_stop["lat"]))
    dist_m = int(math.sqrt(d_lat**2 + d_lon**2))
    speed_mps = max(5.0, (target_v.get("speed_kmh", 35) * 1000 / 3600))
    eta_mins = max(1, int(dist_m / speed_mps / 60))

    return {
        "vehicle_id": target_v["vehicle_id"],
        "route_id": target_v["route_id"],
        "bus_name": target_v.get("bus_name", f"Bus {target_v['route_id']}"),
        "route_color": target_v["route_color"],
        "lat": target_v["lat"],
        "lon": target_v["lon"],
        "speed_kmh": round(target_v["speed_kmh"]),
        "delay_sec": target_v["delay_sec"],
        "delay_text": f"+{round(target_v['delay_sec']/60)}m delay" if target_v["delay_sec"] > 60 else "On Time",
        "occupancy": target_v["occupancy"],
        "distance_m": dist_m,
        "eta_mins": eta_mins
    }

def calculate_single_itinerary(source_id: int, target_id: int, dep_sec: int):
    t_start = time.perf_counter()
    raw_path = raptor_engine.plan_route(source_id, target_id, dep_sec)
    latency_ms = (time.perf_counter() - t_start) * 1000.0

    if not raw_path:
        return None, latency_ms

    formatted_legs = []
    first_board = None
    last_alight = None
    transit_transfers = 0

    for i, leg in enumerate(raw_path):
        b_stop = data_manager.get_stop(leg["board_stop"]) or {"id": leg["board_stop"], "name": f"Stop {leg['board_stop']}", "lat": 0, "lon": 0}
        a_stop = data_manager.get_stop(leg["alight_stop"]) or {"id": leg["alight_stop"], "name": f"Stop {leg['alight_stop']}", "lat": 0, "lon": 0}

        is_walking = (leg["route_id"] == "WALK" or (isinstance(leg["route_id"], int) and leg["route_id"] >= 0xFFFFFFFE))

        if is_walking:
            bus_number = "Walk"
            bus_line_name = "Walk"
            bus_name = "Walk"
            headsign = ""
            action_title = f"Walk to {a_stop['name']}"
            route_color = "#06b6d4"
            route_text_color = "#FFFFFF"
            live_vehicle = None
        else:
            transit_transfers += 1
            raw_rid = str(leg.get("real_route_id", "")).strip()
            route_meta = data_manager.routes.get(raw_rid, {})
            bus_number = route_meta.get("short_name", raw_rid) or raw_rid
            bus_line_name = route_meta.get("long_name", "")
            headsign = leg.get("headsign", "")

            # Combine line name & headsign cleanly
            if bus_line_name and bus_line_name.lower() not in headsign.lower():
                bus_name = f"Bus {bus_number} ({bus_line_name})"
                action_title = f"Catch Bus {bus_number} ({bus_line_name})" + (f" - {headsign}" if headsign else "")
            else:
                bus_name = f"Bus {bus_number}" + (f" ({headsign})" if headsign else "")
                action_title = f"Catch Bus {bus_number}" + (f" - {headsign}" if headsign else "")

            route_color = route_meta.get("color", "#4F46E5")
            route_text_color = route_meta.get("text_color", "#FFFFFF")
            live_vehicle = find_live_vehicle_for_route(bus_number, b_stop)

        if first_board is None:
            first_board = leg["board_time"]
        last_alight = leg["alight_time"]

        duration_sec = max(0, leg["alight_time"] - leg["board_time"])
        duration_mins = max(1, duration_sec // 60)

        # Distance estimation
        d_lat = (a_stop["lat"] - b_stop["lat"]) * 111320
        d_lon = (a_stop["lon"] - b_stop["lon"]) * 111320 * math.cos(math.radians(b_stop["lat"]))
        dist_m = int(math.sqrt(d_lat**2 + d_lon**2))

        stops_count = leg.get("stops_count", 1)
        ride_summary = f"Ride {stops_count} stop{'s' if stops_count > 1 else ''} (~{duration_mins} min)" if not is_walking else f"{dist_m}m walk"

        formatted_legs.append({
            "leg_index": i + 1,
            "is_walking": is_walking,
            "bus_number": bus_number,
            "bus_line_name": bus_line_name,
            "bus_name": bus_name,
            "headsign": headsign,
            "action_title": action_title,
            "route_color": route_color,
            "route_text_color": route_text_color,
            "board_stop": b_stop,
            "alight_stop": a_stop,
            "stops_count": stops_count,
            "ride_summary": ride_summary,
            "intermediate_stops": leg.get("intermediate_stops", []),
            "board_time_sec": leg["board_time"],
            "board_time_formatted": data_manager.sec_to_hms(leg["board_time"]),
            "alight_time_sec": leg["alight_time"],
            "alight_time_formatted": data_manager.sec_to_hms(leg["alight_time"]),
            "duration_mins": duration_mins,
            "distance_m": dist_m,
            "live_vehicle": live_vehicle,
            "geometry": [
                [b_stop.get("lat", 0.0), b_stop.get("lon", 0.0)],
                [a_stop.get("lat", 0.0), a_stop.get("lon", 0.0)]
            ]
        })

    first_board = formatted_legs[0]["board_time_sec"] if formatted_legs else dep_sec
    last_alight = formatted_legs[-1]["alight_time_sec"] if formatted_legs else dep_sec
    total_duration_mins = max(1, (last_alight - first_board) // 60)

    first_bus_sec = None
    first_bus_label = "Direct Transit"
    for leg in formatted_legs:
        if not leg["is_walking"]:
            first_bus_sec = leg["board_time_sec"]
            first_bus_label = leg["bus_name"]
            break

    option = {
        "departure_time": data_manager.sec_to_hms(first_board),
        "arrival_time": data_manager.sec_to_hms(last_alight),
        "total_duration_mins": total_duration_mins,
        "bus_transfers": max(0, transit_transfers - 1),
        "first_bus_label": first_bus_label,
        "departure_sec": first_board,
        "first_bus_sec": first_bus_sec or (first_board + 300),
        "itinerary": formatted_legs
    }
    return option, latency_ms

@app.post("/api/route")
def plan_route(req: RoutePlanRequest):
    dep_sec = 0
    if req.departure_time is None:
        dep_sec = 31620  # Default 08:47 AM
    elif isinstance(req.departure_time, str) and ":" in req.departure_time:
        dep_sec = data_manager.hms_to_sec(req.departure_time)
    else:
        dep_sec = int(req.departure_time)

    source = data_manager.get_stop(req.source_stop)
    target = data_manager.get_stop(req.target_stop)
    if not source or not target:
        raise HTTPException(status_code=400, detail="Invalid starting point or destination")

    options = []
    total_latency_ms = 0.0
    current_search_dep = dep_sec
    num_options = min(5, max(1, req.num_options or 3))

    seen_departure_times = set()

    for _ in range(num_options + 5):
        if len(options) >= num_options:
            break

        opt, latency = calculate_single_itinerary(req.source_stop, req.target_stop, current_search_dep)
        total_latency_ms += latency

        if not opt:
            current_search_dep += 15 * 60
            if current_search_dep > dep_sec + 4 * 3600:
                break
            continue

        dep_key = (opt["departure_time"], opt["arrival_time"])
        if dep_key not in seen_departure_times:
            seen_departure_times.add(dep_key)
            options.append(opt)

        current_search_dep = max(current_search_dep + 120, opt["first_bus_sec"] + 60)

    if not options:
        return {
            "success": False,
            "message": "No bus connections found for this time window. Try selecting another departure time.",
            "source": source,
            "target": target,
            "departure_date": req.departure_date or "today",
            "departure_time": data_manager.sec_to_hms(dep_sec),
            "options": []
        }

    return {
        "success": True,
        "source": source,
        "target": target,
        "departure_date": req.departure_date or "today",
        "departure_time": data_manager.sec_to_hms(dep_sec),
        "options_count": len(options),
        "options": options,
        "itinerary": options[0]["itinerary"],
        "total_duration_mins": options[0]["total_duration_mins"],
        "arrival_time": options[0]["arrival_time"]
    }

@app.get("/api/live/vehicles")
def get_live_vehicles():
    return live_vehicles

# Real-time Background Vehicle Simulator & Broadcaster
async def telemetry_background_worker():
    stops = data_manager.stops
    if not stops:
        return

    # Real Thunder Bay Transit Bus Lines
    active_bus_lines = [
        ("1", "Mainline"),
        ("2", "Crosstown"),
        ("3C", "County Park"),
        ("3M", "Memorial"),
        ("5", "Edward"),
        ("8", "James"),
        ("9", "Junot"),
        ("10", "Northwood"),
        ("11", "John"),
        ("12", "East End"),
        ("14", "Arthur"),
        ("16", "Balmoral"),
        ("17", "Current River"),
        ("18", "Westfort")
    ]
    
    vehicles = []
    for i, (rid, rname) in enumerate(active_bus_lines):
        meta = THUNDER_BAY_ROUTES.get(rid, {})
        color = meta.get("color", "#4F46E5")
        s_from = stops[(i * 35) % len(stops)]
        s_to = stops[(i * 35 + 12) % len(stops)]

        vehicles.append({
            "vehicle_id": f"BUS-{100 + i + 1}",
            "route_id": rid,
            "route_name": rname,
            "bus_name": f"Bus {rid} ({rname})",
            "route_color": color,
            "from_stop": s_from["name"],
            "to_stop": s_to["name"],
            "lat": s_from["lat"],
            "lon": s_from["lon"],
            "target_lat": s_to["lat"],
            "target_lon": s_to["lon"],
            "progress": (i * 0.15) % 1.0,
            "speed_kmh": 32.0 + (i % 12),
            "delay_sec": (i * 25) % 180,
            "occupancy": ["SEATS_AVAILABLE", "SEATS_AVAILABLE", "STANDING_ROOM_ONLY", "EMPTY"][i % 4]
        })

    while True:
        try:
            for v in vehicles:
                v["progress"] += 0.015
                if v["progress"] >= 1.0:
                    v["progress"] = 0.0
                    idx = (int(v["vehicle_id"].split("-")[1]) + int(time.time())) % len(stops)
                    v["from_stop"] = stops[idx]["name"]
                    v["to_stop"] = stops[(idx + 8) % len(stops)]["name"]
                    v["lat"] = stops[idx]["lat"]
                    v["lon"] = stops[idx]["lon"]
                    v["target_lat"] = stops[(idx + 8) % len(stops)]["lat"]
                    v["target_lon"] = stops[(idx + 8) % len(stops)]["lon"]
                else:
                    p = v["progress"]
                    v["current_lat"] = v["lat"] + (v["target_lat"] - v["lat"]) * p
                    v["current_lon"] = v["lon"] + (v["target_lon"] - v["lon"]) * p

            global live_vehicles
            live_vehicles = [
                {
                    "vehicle_id": v["vehicle_id"],
                    "route_id": v["route_id"],
                    "route_name": v["route_name"],
                    "bus_name": v["bus_name"],
                    "route_color": v["route_color"],
                    "lat": v.get("current_lat", v["lat"]),
                    "lon": v.get("current_lon", v["lon"]),
                    "from_stop": v["from_stop"],
                    "to_stop": v["to_stop"],
                    "speed_kmh": v["speed_kmh"],
                    "delay_sec": v["delay_sec"],
                    "occupancy": v["occupancy"]
                }
                for v in vehicles
            ]

            if ws_manager.active_connections:
                payload = {
                    "type": "VEHICLE_POSITIONS",
                    "timestamp": time.time(),
                    "vehicles": live_vehicles
                }
                await ws_manager.broadcast(payload)

        except Exception:
            pass

        await asyncio.sleep(1.5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(telemetry_background_worker())

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "SNAPSHOT",
            "timestamp": time.time(),
            "vehicles": live_vehicles
        })
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
