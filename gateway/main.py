import os
import time
import json
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import grpc

import routing_pb2
import routing_pb2_grpc
from gtfs_data import GTFSDataManager

app = FastAPI(
    title="High-Performance Transit Routing Engine API",
    description="Full-stack C++20 RAPTOR transit engine with live GTFS-RT telemetry and real-time mapping.",
    version="1.0.0"
)

# Enable CORS for web frontend (localhost, Vite dev server, production URLs)
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
    departure_time: Optional[Any] = None  # seconds past midnight or "HH:MM"

class StopDTO(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    raw_id: str

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Web Directory
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
        "version": "1.0.0",
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
        # Ping with zero-cost self query
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
        # Default to simulated current time (e.g., 08:30 = 30600s)
        time_sec = 30600
    departures = data_manager.get_upcoming_departures(stop_id, time_sec)
    # Inject live delay if available
    for dep in departures:
        tid = dep["trip_id"]
        # Match integer trip if available
        if tid in live_delays:
            dep["delay_sec"] = live_delays[tid].get("delay", 0)
    return {
        "stop_id": stop_id,
        "current_time": data_manager.sec_to_hms(time_sec),
        "departures": departures
    }

@app.post("/api/route")
def plan_route(req: RoutePlanRequest):
    t_start = time.perf_counter()
    
    # Parse departure time
    dep_sec = 0
    if req.departure_time is None:
        dep_sec = 30000  # Default 08:20
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
        grpc_req = routing_pb2.RouteRequest(
            source_stop=req.source_stop,
            target_stop=req.target_stop,
            departure_time=dep_sec
        )
        grpc_resp = stub.GetEarliestArrival(grpc_req, timeout=3.0)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"C++ Engine gRPC error: {str(e)}")

    engine_latency_ms = (time.perf_counter() - t_start) * 1000.0

    if not grpc_resp.success or len(grpc_resp.itinerary) == 0:
        return {
            "success": False,
            "message": "No direct transit route found for this departure time. Try selecting an earlier departure.",
            "source": source,
            "target": target,
            "departure_time": data_manager.sec_to_hms(dep_sec),
            "engine_latency_ms": round(engine_latency_ms, 3),
            "itinerary": []
        }

    formatted_legs = []
    total_travel_sec = 0
    first_board = None
    last_alight = None

    for i, leg in enumerate(grpc_resp.itinerary):
        b_stop = data_manager.get_stop(leg.board_stop) or {"id": leg.board_stop, "name": f"Stop {leg.board_stop}", "lat": 0, "lon": 0}
        a_stop = data_manager.get_stop(leg.alight_stop) or {"id": leg.alight_stop, "name": f"Stop {leg.alight_stop}", "lat": 0, "lon": 0}
        
        r_id = str(leg.route_id)
        route_meta = data_manager.routes.get(r_id, {
            "short_name": f"Route {r_id}",
            "color": "#2563EB",
            "text_color": "#FFFFFF"
        })

        if first_board is None:
            first_board = leg.board_time
        last_alight = leg.alight_time

        duration_sec = max(0, leg.alight_time - leg.board_time)
        
        # Coordinates geometry for map polyline
        geometry = [
            [b_stop.get("lat", 0.0), b_stop.get("lon", 0.0)],
            [a_stop.get("lat", 0.0), a_stop.get("lon", 0.0)]
        ]

        formatted_legs.append({
            "leg_index": i + 1,
            "route_id": leg.route_id,
            "route_short_name": route_meta.get("short_name", f"{leg.route_id}"),
            "route_color": route_meta.get("color", "#2563EB"),
            "route_text_color": route_meta.get("text_color", "#FFFFFF"),
            "board_stop": b_stop,
            "alight_stop": a_stop,
            "board_time_sec": leg.board_time,
            "board_time_formatted": data_manager.sec_to_hms(leg.board_time),
            "alight_time_sec": leg.alight_time,
            "alight_time_formatted": data_manager.sec_to_hms(leg.alight_time),
            "duration_mins": max(1, duration_sec // 60),
            "geometry": geometry
        })

    total_duration_mins = max(1, (last_alight - first_board) // 60) if (first_board and last_alight) else 0

    return {
        "success": True,
        "source": source,
        "target": target,
        "departure_time": data_manager.sec_to_hms(first_board or dep_sec),
        "arrival_time": data_manager.sec_to_hms(last_alight or dep_sec),
        "total_duration_mins": total_duration_mins,
        "transfers": max(0, len(formatted_legs) - 1),
        "engine_latency_ms": round(engine_latency_ms, 3),
        "itinerary": formatted_legs
    }

@app.get("/api/live/vehicles")
def get_live_vehicles():
    return live_vehicles

# Real-time Background Vehicle Simulator & Telemetry Broadcaster
async def telemetry_background_worker():
    import math
    stops = data_manager.stops
    if not stops:
        return

    # Seed 15 simulated vehicles operating along stops
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
            # Update positions smoothly
            for v in vehicles:
                v["progress"] += 0.02
                if v["progress"] >= 1.0:
                    v["progress"] = 0.0
                    # Swap or advance to next stop
                    idx = (int(v["vehicle_id"].split("-")[1]) + int(time.time())) % len(stops)
                    v["from_stop"] = stops[idx]["name"]
                    v["to_stop"] = stops[(idx + 4) % len(stops)]["name"]
                    v["lat"] = stops[idx]["lat"]
                    v["lon"] = stops[idx]["lon"]
                    v["target_lat"] = stops[(idx + 4) % len(stops)]["lat"]
                    v["target_lon"] = stops[(idx + 4) % len(stops)]["lon"]
                else:
                    # Linear interpolation
                    p = v["progress"]
                    v["current_lat"] = v["lat"] + (v["target_lat"] - v["lat"]) * p
                    v["current_lon"] = v["lon"] + (v["target_lon"] - v["lon"]) * p

            # Update global state
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

            # Broadcast to WebSockets
            if ws_manager.active_connections:
                payload = {
                    "type": "VEHICLE_POSITIONS",
                    "timestamp": time.time(),
                    "vehicles": live_vehicles
                }
                await ws_manager.broadcast(payload)

        except Exception as e:
            pass

        await asyncio.sleep(1.5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(telemetry_background_worker())

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial snapshot immediately
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
