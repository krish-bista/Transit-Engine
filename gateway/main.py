import os
import time
import json
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import grpc

import routing_pb2
import routing_pb2_grpc
from gtfs_data import GTFSDataManager

app = FastAPI(
    title="High-Performance Transit Routing Engine API",
    description="Full-stack C++20 RAPTOR transit engine with multi-modal footpaths, live GTFS-RT telemetry, and range options.",
    version="1.1.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data Manager
data_manager = GTFSDataManager()

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

def get_grpc_stub():
    host = os.getenv("ENGINE_HOST", "172.19.182.96")
    port = int(os.getenv("ENGINE_PORT", "50051"))
    channel = grpc.insecure_channel(f"{host}:{port}")
    return routing_pb2_grpc.RoutingEngineStub(channel)

# Pydantic Schemas
class RoutePlanRequest(BaseModel):
    source_stop: int
    target_stop: int
    departure_time: Optional[Any] = None  # "08:47" or seconds
    departure_date: Optional[str] = "today" # "today", "tomorrow", "YYYY-MM-DD"
    num_options: Optional[int] = 3

class StopDTO(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    raw_id: str

# Web Directory Static Files
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/", include_in_schema=False)
def serve_root():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "system": "Transit Engine",
        "version": "1.1.0",
        "status": "online",
        "stops_loaded": len(data_manager.stops),
        "routes_loaded": len(data_manager.routes)
    }

@app.get("/styles.css", include_in_schema=False)
def serve_styles():
    return FileResponse(os.path.join(WEB_DIR, "styles.css"))

@app.get("/app.js", include_in_schema=False)
def serve_app_js():
    return FileResponse(os.path.join(WEB_DIR, "app.js"))

@app.get("/api/health")
def health():
    engine_ok = False
    try:
        stub = get_grpc_stub()
        resp = stub.GetEarliestArrival(
            routing_pb2.RouteRequest(source_stop=0, target_stop=0, departure_time=36000),
            timeout=1.0
        )
        engine_ok = resp.success
    except Exception:
        engine_ok = False

    return {
        "status": "healthy" if engine_ok else "degraded",
        "grpc_engine": "connected" if engine_ok else "unreachable",
        "stops_count": len(data_manager.stops),
        "active_ws_clients": len(ws_manager.active_connections),
        "live_vehicles_count": len(live_vehicles)
    }

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
        time_sec = 30600 # 08:30 default
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

def calculate_single_itinerary(stub, source_id: int, target_id: int, dep_sec: int):
    t_start = time.perf_counter()
    try:
        grpc_req = routing_pb2.RouteRequest(
            source_stop=source_id,
            target_stop=target_id,
            departure_time=dep_sec
        )
        grpc_resp = stub.GetEarliestArrival(grpc_req, timeout=1.5)
    except Exception as e:
        return None, (time.perf_counter() - t_start) * 1000.0

    latency_ms = (time.perf_counter() - t_start) * 1000.0

    if not grpc_resp.success or len(grpc_resp.itinerary) == 0:
        return None, latency_ms

    formatted_legs = []
    first_board = None
    last_alight = None
    transit_transfers = 0

    for i, leg in enumerate(grpc_resp.itinerary):
        b_stop = data_manager.get_stop(leg.board_stop) or {"id": leg.board_stop, "name": f"Stop {leg.board_stop}", "lat": 0, "lon": 0}
        a_stop = data_manager.get_stop(leg.alight_stop) or {"id": leg.alight_stop, "name": f"Stop {leg.alight_stop}", "lat": 0, "lon": 0}
        
        is_walking = (leg.route_id >= 0xFFFFFFFE)
        r_id = str(leg.route_id)
        
        if is_walking:
            route_short_name = "Walk"
            route_color = "#64748B"
            route_text_color = "#FFFFFF"
        else:
            transit_transfers += 1
            route_meta = data_manager.routes.get(r_id, {
                "short_name": f"{leg.route_id}",
                "color": "#4F46E5",
                "text_color": "#FFFFFF"
            })
            route_short_name = route_meta.get("short_name", f"{leg.route_id}")
            route_color = route_meta.get("color", "#4F46E5")
            route_text_color = route_meta.get("text_color", "#FFFFFF")

        if first_board is None:
            first_board = leg.board_time
        last_alight = leg.alight_time

        duration_sec = max(0, leg.alight_time - leg.board_time)
        duration_mins = max(1, duration_sec // 60)

        # Distance estimation
        import math
        d_lat = (a_stop["lat"] - b_stop["lat"]) * 111320
        d_lon = (a_stop["lon"] - b_stop["lon"]) * 111320 * math.cos(math.radians(b_stop["lat"]))
        dist_m = int(math.sqrt(d_lat**2 + d_lon**2))

        instruction = f"Walk {duration_mins} min ({dist_m}m) to {a_stop['name']}" if is_walking else f"Take Route {route_short_name} to {a_stop['name']}"

        formatted_legs.append({
            "leg_index": i + 1,
            "is_walking": is_walking,
            "route_id": leg.route_id,
            "route_short_name": route_short_name,
            "route_color": route_color,
            "route_text_color": route_text_color,
            "board_stop": b_stop,
            "alight_stop": a_stop,
            "board_time_sec": leg.board_time,
            "board_time_formatted": data_manager.sec_to_hms(leg.board_time),
            "alight_time_sec": leg.alight_time,
            "alight_time_formatted": data_manager.sec_to_hms(leg.alight_time),
            "duration_mins": duration_mins,
            "distance_m": dist_m,
            "instruction": instruction,
            "geometry": [
                [b_stop.get("lat", 0.0), b_stop.get("lon", 0.0)],
                [a_stop.get("lat", 0.0), a_stop.get("lon", 0.0)]
            ]
        })

    first_board = formatted_legs[0]["board_time_sec"] if formatted_legs else dep_sec
    last_alight = formatted_legs[-1]["alight_time_sec"] if formatted_legs else dep_sec
    total_duration_mins = max(1, (last_alight - first_board) // 60)

    # First transit bus boarding time
    first_bus_sec = None
    for leg in formatted_legs:
        if not leg["is_walking"]:
            first_bus_sec = leg["board_time_sec"]
            break

    option = {
        "departure_time": data_manager.sec_to_hms(first_board),
        "arrival_time": data_manager.sec_to_hms(last_alight),
        "total_duration_mins": total_duration_mins,
        "bus_transfers": max(0, transit_transfers - 1),
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
        raise HTTPException(status_code=400, detail="Invalid source or target stop ID")

    try:
        stub = get_grpc_stub()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"C++ Engine gRPC connection error: {str(e)}")

    options = []
    total_latency_ms = 0.0
    current_search_dep = dep_sec
    num_options = min(5, max(1, req.num_options or 3))

    seen_departure_times = set()

    for _ in range(num_options + 5):
        if len(options) >= num_options:
            break

        opt, latency = calculate_single_itinerary(stub, req.source_stop, req.target_stop, current_search_dep)
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

        # Advance search window past the boarded bus trip
        current_search_dep = max(current_search_dep + 120, opt["first_bus_sec"] + 60)

    if not options:
        return {
            "success": False,
            "message": "No transit connections found for this time window. Try selecting another time.",
            "source": source,
            "target": target,
            "departure_date": req.departure_date or "today",
            "departure_time": data_manager.sec_to_hms(dep_sec),
            "engine_latency_ms": round(total_latency_ms, 3),
            "options": []
        }

    return {
        "success": True,
        "source": source,
        "target": target,
        "departure_date": req.departure_date or "today",
        "departure_time": data_manager.sec_to_hms(dep_sec),
        "engine_latency_ms": round(total_latency_ms, 3),
        "options_count": len(options),
        "options": options,
        "itinerary": options[0]["itinerary"],
        "total_duration_mins": options[0]["total_duration_mins"],
        "arrival_time": options[0]["arrival_time"]
    }

@app.get("/api/live/vehicles")
def get_live_vehicles():
    return live_vehicles

# Real-time Background Vehicle Simulator & Telemetry Broadcaster
async def telemetry_background_worker():
    stops = data_manager.stops
    if not stops:
        return

    num_vehicles = min(15, len(stops) - 5)
    vehicles = []
    for i in range(num_vehicles):
        s_from = stops[i * 10 % len(stops)]
        s_to = stops[(i * 10 + 5) % len(stops)]
        vehicles.append({
            "vehicle_id": f"BUS-{101 + i}",
            "route_id": f"{(i % 8) + 1}",
            "route_color": ["#EF4135", "#13B5EA", "#BF4F9D", "#00B259", "#F26531", "#9C0059", "#8DC63F", "#E58E1A"][i % 8],
            "from_stop": s_from["name"],
            "to_stop": s_to["name"],
            "lat": s_from["lat"],
            "lon": s_from["lon"],
            "target_lat": s_to["lat"],
            "target_lon": s_to["lon"],
            "progress": (i * 0.1) % 1.0,
            "speed_kmh": 35.0 + (i % 15),
            "delay_sec": (i * 45) % 300,
            "occupancy": ["EMPTY", "MANY_SEATS_AVAILABLE", "FEW_SEATS_AVAILABLE", "STANDING_ROOM_ONLY"][i % 4]
        })

    while True:
        try:
            for v in vehicles:
                v["progress"] += 0.02
                if v["progress"] >= 1.0:
                    v["progress"] = 0.0
                    idx = (int(v["vehicle_id"].split("-")[1]) + int(time.time())) % len(stops)
                    v["from_stop"] = stops[idx]["name"]
                    v["to_stop"] = stops[(idx + 4) % len(stops)]["name"]
                    v["lat"] = stops[idx]["lat"]
                    v["lon"] = stops[idx]["lon"]
                    v["target_lat"] = stops[(idx + 4) % len(stops)]["lat"]
                    v["target_lon"] = stops[(idx + 4) % len(stops)]["lon"]
                else:
                    p = v["progress"]
                    v["current_lat"] = v["lat"] + (v["target_lat"] - v["lat"]) * p
                    v["current_lon"] = v["lon"] + (v["target_lon"] - v["lon"]) * p

            global live_vehicles
            live_vehicles = [
                {
                    "vehicle_id": v["vehicle_id"],
                    "route_id": v["route_id"],
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
