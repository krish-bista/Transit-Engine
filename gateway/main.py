import os
import sys
import time
import math
import asyncio
from typing import List, Dict, Any, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from datetime import datetime
try:
    import zoneinfo
    TBAY_TZ = zoneinfo.ZoneInfo("America/Toronto")
except Exception:
    TBAY_TZ = None

def get_thunder_bay_time() -> int:
    if TBAY_TZ:
        now = datetime.now(TBAY_TZ)
        return now.hour * 3600 + now.minute * 60 + now.second
    utc = datetime.utcnow()
    h = (utc.hour - 4) % 24
    return h * 3600 + utc.minute * 60 + utc.second

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from gateway.gtfs_data import GTFSDataManager, THUNDER_BAY_ROUTES
    from gateway.raptor_engine import RaptorEngine
except ImportError:
    from gtfs_data import GTFSDataManager, THUNDER_BAY_ROUTES
    from raptor_engine import RaptorEngine

app = FastAPI(title="Transit Engine", version="2.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

data_manager = GTFSDataManager()
raptor_engine = RaptorEngine(data_manager.stops, data_manager.stop_times, data_manager.routes, data_manager.trips)

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

live_delays: Dict[int, Dict[str, Any]] = {}
live_vehicles: List[Dict[str, Any]] = []

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

WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/", include_in_schema=False)
def serve_root():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"system": "City Transit", "version": "2.5.0", "status": "online"}

@app.get("/styles.css", include_in_schema=False)
def serve_styles():
    return FileResponse(os.path.join(WEB_DIR, "styles.css"))

@app.get("/app.js", include_in_schema=False)
def serve_app_js():
    return FileResponse(os.path.join(WEB_DIR, "app.js"))

@app.get("/manifest.json", include_in_schema=False)
def serve_manifest():
    return FileResponse(os.path.join(WEB_DIR, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js", include_in_schema=False)
def serve_sw():
    return FileResponse(os.path.join(WEB_DIR, "sw.js"), media_type="application/javascript",
                       headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

@app.get("/icons/{icon_name}", include_in_schema=False)
def serve_icon(icon_name: str):
    icon_path = os.path.join(WEB_DIR, "icons", icon_name)
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png")
    return {"error": "Icon not found"}

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "stops_count": len(data_manager.stops),
        "routes_count": len(raptor_engine.routes),
        "active_ws_clients": len(ws_manager.active_connections),
        "live_vehicles_count": len(live_vehicles)
    }

@app.get("/api/nearest-stop")
def get_nearest_stop(lat: float, lon: float):
    stop = data_manager.find_nearest_stop(lat, lon)
    if not stop:
        raise HTTPException(status_code=404, detail="No nearby bus stop found")
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
        time_sec = get_thunder_bay_time()
    departures = data_manager.get_upcoming_departures(stop_id, time_sec)
    for dep in departures:
        tid = dep["trip_id"]
        if tid in live_delays:
            dep["delay_sec"] = live_delays[tid].get("delay_sec", 0)
    return {"stop_id": stop_id, "departures": departures}

def find_live_vehicle_for_trip(trip_id: Optional[str], bus_number: str, board_stop: dict) -> Optional[dict]:
    b_num = str(bus_number).strip().upper()
    best_v = None
    min_d = float("inf")

    for v in live_vehicles:
        if trip_id and v.get("trip_id") == trip_id:
            best_v = dict(v)
            d_lat = (v["lat"] - board_stop["lat"]) * 111320
            d_lon = (v["lon"] - board_stop["lon"]) * 111320 * math.cos(math.radians(board_stop["lat"]))
            dist = int(math.sqrt(d_lat**2 + d_lon**2))
            best_v["distance_to_stop_m"] = dist
            best_v["eta_minutes"] = max(1, int(dist / 9.5 / 60))
            return best_v

        v_rid = str(v.get("route_id", "")).strip().upper()
        if v_rid == b_num:
            d_lat = (v["lat"] - board_stop["lat"]) * 111320
            d_lon = (v["lon"] - board_stop["lon"]) * 111320 * math.cos(math.radians(board_stop["lat"]))
            dist = int(math.sqrt(d_lat**2 + d_lon**2))
            if dist < min_d:
                min_d = dist
                best_v = dict(v)
                best_v["distance_to_stop_m"] = dist
                best_v["eta_minutes"] = max(1, int(dist / 9.5 / 60))

    return best_v

def calculate_single_itinerary(source_id: int, target_id: int, dep_sec: int):
    t0 = time.time()
    itinerary_raw = raptor_engine.plan_route(source_id, target_id, dep_sec)
    latency_ms = round((time.time() - t0) * 1000, 2)

    if not itinerary_raw:
        return None, latency_ms

    first_bus_boarding_sec = None
    for leg in itinerary_raw:
        is_walk = (leg["route_id"] == "WALK" or (isinstance(leg["route_id"], int) and leg["route_id"] >= 0xFFFFFFFE))
        if not is_walk:
            first_bus_boarding_sec = leg["board_time"]
            break

    formatted_legs = []
    first_board = None
    last_alight = None
    physical_transfers = 0

    for i, leg in enumerate(itinerary_raw):
        b_stop = data_manager.get_stop(leg["board_stop"]) or {"id": leg["board_stop"], "name": f"Stop {leg['board_stop']}", "lat": 0, "lon": 0}
        a_stop = data_manager.get_stop(leg["alight_stop"]) or {"id": leg["alight_stop"], "name": f"Stop {leg['alight_stop']}", "lat": 0, "lon": 0}

        is_walking = (leg["route_id"] == "WALK" or (isinstance(leg["route_id"], int) and leg["route_id"] >= 0xFFFFFFFE))
        is_stay_on_bus = False

        if is_walking:
            bus_number = "Walk"
            bus_line_name = "Walk"
            bus_name = "Walk"
            headsign = ""
            action_title = f"Walk to {a_stop['name']}"
            route_color = "#0ea5e9"
            route_text_color = "#FFFFFF"
            live_vehicle = None
            leg_geometry = [
                [b_stop.get("lat", 0.0), b_stop.get("lon", 0.0)],
                [a_stop.get("lat", 0.0), a_stop.get("lon", 0.0)]
            ]

            if i == 0 and first_bus_boarding_sec is not None:
                walk_duration = max(60, leg["alight_time"] - leg["board_time"])
                leg["alight_time"] = first_bus_boarding_sec
                leg["board_time"] = max(dep_sec, first_bus_boarding_sec - walk_duration)
        else:
            raw_rid = str(leg.get("real_route_id", "")).strip()
            route_meta = data_manager.routes.get(raw_rid, {})
            bus_number = route_meta.get("short_name", raw_rid) or raw_rid
            bus_line_name = route_meta.get("long_name", "")
            headsign = leg.get("headsign", "")

            prev_transit_leg = None
            for prev in reversed(formatted_legs):
                if not prev["is_walking"]:
                    prev_transit_leg = prev
                    break

            if prev_transit_leg:
                p_tid = prev_transit_leg.get("trip_id")
                c_tid = leg.get("trip_id")
                p_meta = data_manager.trips.get(p_tid, {})
                c_meta = data_manager.trips.get(c_tid, {})
                p_block = p_meta.get("block_id")
                c_block = c_meta.get("block_id")
                if (p_block and c_block and p_block == c_block) or (prev_transit_leg["alight_stop"]["id"] == b_stop["id"] and abs(leg["board_time"] - prev_transit_leg["alight_time_sec"]) <= 300):
                    is_stay_on_bus = True

            if is_stay_on_bus and prev_transit_leg:
                bus_name = f"Bus {bus_number}" + (f" ({headsign})" if headsign else "")
                action_title = f"Stay on board • Bus {prev_transit_leg['bus_number']} continues as Route {bus_number} ({bus_line_name or headsign})"
            elif bus_line_name and bus_line_name.lower() not in headsign.lower():
                bus_name = f"Bus {bus_number} ({bus_line_name})"
                action_title = f"Take the {bus_number} {bus_line_name} bus"
                physical_transfers += 1
            else:
                bus_name = f"Bus {bus_number}" + (f" ({headsign})" if headsign else "")
                action_title = f"Take the {bus_number} bus" + (f" ({headsign})" if headsign else "")
                physical_transfers += 1

            route_color = route_meta.get("color", "#4338CA")
            route_text_color = route_meta.get("text_color", "#FFFFFF")
            live_vehicle = find_live_vehicle_for_trip(leg.get("trip_id"), bus_number, b_stop)

            leg_geometry = data_manager.get_shape_segment(raw_rid, b_stop["lat"], b_stop["lon"], a_stop["lat"], a_stop["lon"])
            if len(leg_geometry) <= 2 and bus_number:
                leg_geometry = data_manager.get_shape_segment(bus_number, b_stop["lat"], b_stop["lon"], a_stop["lat"], a_stop["lon"])

        if first_board is None:
            first_board = leg["board_time"]
        last_alight = leg["alight_time"]

        duration_sec = max(0, leg["alight_time"] - leg["board_time"])
        duration_mins = max(1, duration_sec // 60)

        d_lat = (a_stop["lat"] - b_stop["lat"]) * 111320
        d_lon = (a_stop["lon"] - b_stop["lon"]) * 111320 * math.cos(math.radians(b_stop["lat"]))
        dist_m = int(math.sqrt(d_lat**2 + d_lon**2))

        stops_count = leg.get("stops_count", 1)
        if is_stay_on_bus:
            ride_summary = f"Stay on board ({stops_count} stops • ~{duration_mins} min)"
        elif is_walking:
            ride_summary = f"{dist_m}m walk"
        else:
            ride_summary = f"Ride {stops_count} stop{'s' if stops_count > 1 else ''} (~{duration_mins} min)"

        formatted_legs.append({
            "leg_index": i + 1,
            "is_walking": is_walking,
            "is_stay_on_bus": is_stay_on_bus,
            "trip_id": leg.get("trip_id"),
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
            "geometry": leg_geometry
        })

    first_board = formatted_legs[0]["board_time_sec"] if formatted_legs else dep_sec
    last_alight = formatted_legs[-1]["alight_time_sec"] if formatted_legs else dep_sec
    total_duration_mins = max(1, (last_alight - first_board) // 60)

    first_bus_sec = None
    first_bus_label = "Direct Ride"
    for leg in formatted_legs:
        if not leg["is_walking"]:
            first_bus_sec = leg["board_time_sec"]
            first_bus_label = leg["bus_name"]
            break

    option = {
        "departure_time": data_manager.sec_to_hms(first_board),
        "arrival_time": data_manager.sec_to_hms(last_alight),
        "total_duration_mins": total_duration_mins,
        "bus_transfers": max(0, physical_transfers - 1),
        "first_bus_label": first_bus_label,
        "departure_sec": first_board,
        "first_bus_sec": first_bus_sec or (first_board + 300),
        "itinerary": formatted_legs
    }
    return option, latency_ms

@app.post("/api/route")
def plan_route(req: RoutePlanRequest):
    dep_sec = 0
    if req.departure_time is None or req.departure_time == "now":
        dep_sec = get_thunder_bay_time()
    elif isinstance(req.departure_time, str) and ":" in req.departure_time:
        dep_sec = data_manager.hms_to_sec(req.departure_time)
    else:
        try:
            dep_sec = int(req.departure_time)
        except Exception:
            dep_sec = get_thunder_bay_time()

    source = data_manager.get_stop(req.source_stop)
    target = data_manager.get_stop(req.target_stop)
    if not source or not target:
        raise HTTPException(status_code=400, detail="Invalid starting location or destination")

    options = []
    total_latency_ms = 0.0
    current_search_dep = dep_sec
    num_options = min(5, max(1, req.num_options or 3))

    seen_departure_times = set()

    for _ in range(num_options + 20):
        if len(options) >= num_options:
            break

        opt, latency = calculate_single_itinerary(req.source_stop, req.target_stop, current_search_dep)
        total_latency_ms += latency

        if not opt:
            current_search_dep += 15 * 60
            if current_search_dep > dep_sec + 14 * 3600:
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
            "message": "No bus connections found for this time. Try selecting a different time or nearby stop.",
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

async def telemetry_background_worker():
    stops = data_manager.stops
    if not stops:
        return

    while True:
        try:
            if TBAY_TZ:
                now = datetime.now(TBAY_TZ)
            else:
                now = datetime.utcnow()
            current_sec = get_thunder_bay_time()
            date_str = now.strftime("%Y%m%d")
            dow = now.weekday()

            active_fleet = data_manager.get_live_active_vehicles(current_sec, date_str, dow)

            global live_vehicles
            live_vehicles = active_fleet

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
