// Global State
let map;
let stopsData = [];
let routesData = [];
let sourceStopId = 217; // Edward & Gordon
let targetStopId = 184; // Thunder Bay Regional Hospital
let busMarkers = {};
let routePolylineLayer = null;
let stopMarkersLayer = null;
let trackingPolylineLayer = null;
let showStopPins = true;
let currentRouteData = null;
let selectedOptionIndex = 0;
let trackedVehicleId = null;
let trackedBoardStop = null;
let ws;

// Initialize when DOM loads
document.addEventListener("DOMContentLoaded", async () => {
  lucide.createIcons();
  initMap();
  updateClock();
  setInterval(updateClock, 1000);

  await loadStops();
  await loadRoutes();
  initWebSocket();

  // Set default names in inputs
  const sStop = stopsData.find(s => s.id === sourceStopId);
  const tStop = stopsData.find(s => s.id === targetStopId);
  if (sStop) {
    document.getElementById("source-input").value = sStop.name;
  }
  if (tStop) {
    document.getElementById("target-input").value = tStop.name;
  }

  setupAutocomplete("source-input", "source-results", (stop) => {
    sourceStopId = stop.id;
    highlightStopOnMap(stop, true);
  });

  setupAutocomplete("target-input", "target-results", (stop) => {
    targetStopId = stop.id;
    highlightStopOnMap(stop, false);
  });

  // Calculate default route immediately
  calculateRoute();
});

// Map Setup
function initMap() {
  map = L.map("map", {
    zoomControl: false,
    attributionControl: false
  }).setView([48.416, -89.236], 13);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    subdomains: "abcd"
  }).addTo(map);

  L.control.zoom({ position: "bottomright" }).addTo(map);

  stopMarkersLayer = L.layerGroup().addTo(map);
  routePolylineLayer = L.layerGroup().addTo(map);
  trackingPolylineLayer = L.layerGroup().addTo(map);
}

function centerMapOnTransit() {
  if (map) {
    map.setView([48.416, -89.236], 13);
  }
}

// Current Location Geolocation Handler
async function useCurrentLocation() {
  const input = document.getElementById("source-input");
  input.value = "Locating your position...";

  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    input.value = "Edward & Gordon";
    return;
  }

  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;

      try {
        const res = await fetch(`/api/nearest-stop?lat=${lat}&lon=${lon}`);
        if (!res.ok) throw new Error("Failed to find nearest stop");
        const nearest = await res.json();

        sourceStopId = nearest.id;
        input.value = `${nearest.name} (~${nearest.distance_m || 50}m away)`;
        highlightStopOnMap(nearest, true);
        calculateRoute();
      } catch (err) {
        input.value = "Edward & Gordon";
        sourceStopId = 217;
      }
    },
    (err) => {
      // Fallback on permission denied
      input.value = "Edward & Gordon (Near You)";
      sourceStopId = 217;
      calculateRoute();
    },
    { timeout: 6000 }
  );
}

// Load Stops from Gateway
async function loadStops() {
  try {
    const res = await fetch("/api/stops");
    if (!res.ok) throw new Error("Failed to fetch stops");
    stopsData = await res.json();
    document.getElementById("metric-stops-count").innerText = stopsData.length.toLocaleString();
    renderStopPins();
  } catch (err) {
    console.error("Error loading stops:", err);
  }
}

// Load Routes
async function loadRoutes() {
  try {
    const res = await fetch("/api/routes");
    if (!res.ok) return;
    routesData = await res.json();
  } catch (err) {
    console.error("Error loading routes:", err);
  }
}

// Render Stop Pins
function renderStopPins() {
  stopMarkersLayer.clearLayers();
  if (!showStopPins) return;

  stopsData.forEach(stop => {
    let pinClass = "stop-pin";
    if (stop.id === sourceStopId) pinClass += " origin";
    if (stop.id === targetStopId) pinClass += " destination";

    const icon = L.divIcon({
      className: "stop-pin-wrapper",
      html: `<div class="${pinClass}" title="${stop.name}"></div>`,
      iconSize: [12, 12],
      iconAnchor: [6, 6]
    });

    const marker = L.marker([stop.lat, stop.lon], { icon });
    marker.bindPopup(`
      <div class="p-2 space-y-1.5 text-slate-900 font-sans">
        <h4 class="font-bold text-sm">${stop.name}</h4>
        <span class="text-xs text-slate-500 font-mono">Stop #${stop.id}</span>
        <div class="flex space-x-2 pt-2">
          <button onclick="setAsOrigin(${stop.id})" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-xs font-semibold">Start Here</button>
          <button onclick="setAsDestination(${stop.id})" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded text-xs font-semibold">Go Here</button>
          <button onclick="openDeparturesModal(${stop.id})" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold">Live Buses</button>
        </div>
      </div>
    `);
    stopMarkersLayer.addLayer(marker);
  });
}

function toggleAllStops() {
  showStopPins = !showStopPins;
  renderStopPins();
  const btn = document.getElementById("toggle-stops-btn");
  btn.classList.toggle("text-slate-400", !showStopPins);
  btn.classList.toggle("text-indigo-400", showStopPins);
}

function setAsOrigin(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (stop) {
    sourceStopId = stop.id;
    document.getElementById("source-input").value = stop.name;
    map.closePopup();
    renderStopPins();
    calculateRoute();
  }
}

function setAsDestination(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (stop) {
    targetStopId = stop.id;
    document.getElementById("target-input").value = stop.name;
    map.closePopup();
    renderStopPins();
    calculateRoute();
  }
}

function highlightStopOnMap(stop, isOrigin = true) {
  if (map && stop.lat && stop.lon) {
    map.flyTo([stop.lat, stop.lon], 15, { duration: 1.0 });
    renderStopPins();
  }
}

// Autocomplete Helper
function setupAutocomplete(inputId, resultsId, onSelect) {
  const input = document.getElementById(inputId);
  const results = document.getElementById(resultsId);

  input.addEventListener("input", () => {
    const q = input.value.toLowerCase().trim();
    if (!q) {
      results.classList.add("hidden");
      return;
    }

    const matches = stopsData.filter(s => 
      s.name.toLowerCase().includes(q) || String(s.id).includes(q)
    ).slice(0, 8);

    if (matches.length === 0) {
      results.innerHTML = `<div class="p-3 text-xs text-slate-500">No stops found. Try typing a street or landmark name.</div>`;
      results.classList.remove("hidden");
      return;
    }

    results.innerHTML = matches.map(s => `
      <div class="p-2.5 hover:bg-slate-800 cursor-pointer border-b border-slate-800/50 flex items-center justify-between transition"
           onclick="selectStop('${inputId}', '${resultsId}', ${s.id})">
        <div>
          <p class="text-sm font-medium text-slate-200">${s.name}</p>
          <span class="text-[10px] text-slate-500 font-mono">Stop #${s.id}</span>
        </div>
        <span class="text-xs text-indigo-400 font-medium">Select</span>
      </div>
    `).join("");

    results.classList.remove("hidden");
  });

  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.classList.add("hidden");
    }
  });
}

function selectStop(inputId, resultsId, stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (stop) {
    document.getElementById(inputId).value = stop.name;
    document.getElementById(resultsId).classList.add("hidden");
    if (inputId === "source-input") {
      sourceStopId = stop.id;
    } else {
      targetStopId = stop.id;
    }
    highlightStopOnMap(stop, inputId === "source-input");
    calculateRoute();
  }
}

function swapStops() {
  const tempId = sourceStopId;
  sourceStopId = targetStopId;
  targetStopId = tempId;

  const sStop = stopsData.find(s => s.id === sourceStopId);
  const tStop = stopsData.find(s => s.id === targetStopId);

  document.getElementById("source-input").value = sStop ? sStop.name : "";
  document.getElementById("target-input").value = tStop ? tStop.name : "";
  renderStopPins();
  calculateRoute();
}

function setTimePreset(timeStr) {
  document.getElementById("departure-time").value = timeStr;
  calculateRoute();
}

function setNowTime() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  document.getElementById("departure-time").value = `${h}:${m}`;
  calculateRoute();
}

// Calculate Route with Passenger Directions
async function calculateRoute() {
  const btn = document.getElementById("search-route-btn");
  const container = document.getElementById("route-results-container");
  const depTime = document.getElementById("departure-time").value || "08:47";
  const depDate = document.getElementById("departure-date").value || "tomorrow";

  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-white"></i><span>Finding Buses...</span>`;
  lucide.createIcons();

  try {
    const res = await fetch("/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_stop: sourceStopId,
        target_stop: targetStopId,
        departure_time: depTime,
        departure_date: depDate,
        num_options: 3
      })
    });

    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="compass" class="w-4 h-4 text-white"></i><span>Find Best Bus Options</span>`;
    lucide.createIcons();

    if (!data.success || !data.options || data.options.length === 0) {
      container.innerHTML = `
        <div class="bg-amber-950/30 border border-amber-500/30 p-4 rounded-xl text-amber-300 text-xs space-y-1">
          <p class="font-bold">No Bus Connections Found</p>
          <p>${data.message || "Try picking another time or nearby stops."}</p>
        </div>
      `;
      routePolylineLayer.clearLayers();
      return;
    }

    currentRouteData = data;
    selectedOptionIndex = 0;
    document.getElementById("avg-latency-display").innerText = `${data.engine_latency_ms} ms`;

    renderOptionsAndItinerary();

  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="compass" class="w-4 h-4 text-white"></i><span>Find Best Bus Options</span>`;
    lucide.createIcons();
    container.innerHTML = `
      <div class="bg-rose-950/30 border border-rose-500/30 p-4 rounded-xl text-rose-300 text-xs">
        <p class="font-bold">Routing Error</p>
        <p>${err.message}</p>
      </div>
    `;
  }
}

function selectOption(index) {
  selectedOptionIndex = index;
  renderOptionsAndItinerary();
}

function renderOptionsAndItinerary() {
  if (!currentRouteData || !currentRouteData.options) return;
  const container = document.getElementById("route-results-container");
  const options = currentRouteData.options;
  const currentOpt = options[selectedOptionIndex] || options[0];

  // Options Pills
  const optionsPillsHtml = options.map((opt, idx) => {
    const isSelected = (idx === selectedOptionIndex);
    return `
      <button onclick="selectOption(${idx})"
              class="flex-1 p-2.5 rounded-xl border text-left transition ${isSelected ? 'bg-indigo-600/20 border-indigo-500 text-white shadow-lg' : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'}">
        <div class="flex items-center justify-between">
          <span class="text-[10px] uppercase font-bold tracking-wider ${isSelected ? 'text-indigo-400' : 'text-slate-500'}">Option ${idx + 1}</span>
          <span class="text-[11px] font-bold ${isSelected ? 'text-cyan-400' : 'text-slate-400'}">${opt.total_duration_mins}m</span>
        </div>
        <p class="text-xs font-bold mt-0.5 text-white">${opt.departure_time} → ${opt.arrival_time}</p>
        <span class="text-[10px] text-slate-400">${opt.first_bus_label || 'Direct'}</span>
      </button>
    `;
  }).join("");

  // Step-by-Step Legs
  const legsHtml = currentOpt.itinerary.map((leg, lIdx) => {
    if (leg.is_walking) {
      return `
        <div class="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3 flex items-center space-x-3">
          <div class="w-8 h-8 rounded-lg bg-cyan-950/60 border border-cyan-500/30 text-cyan-400 flex items-center justify-center shrink-0">
            <i data-lucide="footprints" class="w-4 h-4"></i>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between">
              <p class="text-xs font-semibold text-slate-200 truncate">${leg.instruction}</p>
              <span class="text-xs text-slate-400 font-mono">${leg.duration_mins} min</span>
            </div>
            <span class="text-[10px] text-slate-500 font-mono">${leg.board_time_formatted} → ${leg.alight_time_formatted}</span>
          </div>
        </div>
      `;
    }

    const liveVeh = leg.live_vehicle;
    const trackBtnHtml = liveVeh ? `
      <button onclick="trackBus('${liveVeh.vehicle_id}', '${leg.bus_number}', ${leg.board_stop.lat}, ${leg.board_stop.lon}, '${leg.bus_name}')"
              class="w-full mt-2 py-2 px-3 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-bold text-xs rounded-xl shadow-lg flex items-center justify-center space-x-2 transition">
        <span class="w-2 h-2 rounded-full bg-white animate-ping"></span>
        <span>🔴 Live Track Bus ${leg.bus_number} (ETA ~${liveVeh.eta_mins} min)</span>
      </button>
    ` : `
      <button onclick="highlightBusRoute('${leg.bus_number}')"
              class="w-full mt-2 py-1.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs rounded-xl transition flex items-center justify-center space-x-1.5">
        <i data-lucide="eye" class="w-3.5 h-3.5"></i>
        <span>Show Bus ${leg.bus_number} Path</span>
      </button>
    `;

    return `
      <div class="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-2xl p-4 space-y-3 transition shadow-lg">
        
        <!-- Header: Hop on Bus X -->
        <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
          <div class="flex items-center space-x-2.5">
            <span class="px-3 py-1 rounded-xl text-sm font-black shadow-md text-white flex items-center space-x-1"
                  style="background-color: ${leg.route_color}">
              <i data-lucide="bus" class="w-4 h-4 mr-1"></i>
              <span>BUS ${leg.bus_number}</span>
            </span>
            <div>
              <h4 class="text-sm font-bold text-white leading-tight">${leg.headsign ? leg.headsign : `Bus Line ${leg.bus_number}`}</h4>
              <span class="text-[11px] text-emerald-400 font-medium">Departs at ${leg.board_time_formatted}</span>
            </div>
          </div>
          <span class="text-xs font-bold text-slate-300 bg-slate-800 px-2 py-1 rounded-lg mono">${leg.duration_mins} min</span>
        </div>

        <!-- Boarding & Alighting Details -->
        <div class="relative pl-6 space-y-3.5 border-l-2 border-indigo-500/60 ml-2.5 py-1">
          
          <!-- Boarding Stop -->
          <div class="relative">
            <span class="absolute -left-[31px] top-1 w-3.5 h-3.5 rounded-full border-2 border-white bg-indigo-600 shadow-md"></span>
            <div>
              <span class="text-[10px] text-indigo-400 font-bold uppercase tracking-wider block">Board At</span>
              <p class="text-xs font-bold text-white">${leg.board_stop.name}</p>
              <span class="text-[11px] text-slate-400 font-mono">Time: ${leg.board_time_formatted}</span>
            </div>
          </div>

          <!-- Ride Summary -->
          <div class="text-xs text-slate-400 bg-slate-950/80 px-3 py-1.5 rounded-lg border border-slate-800/80 flex items-center justify-between">
            <span>🚌 ${leg.ride_summary}</span>
            <span class="text-slate-500 text-[10px]">Sit back & relax</span>
          </div>

          <!-- Alighting Stop -->
          <div class="relative">
            <span class="absolute -left-[31px] top-1 w-3.5 h-3.5 rounded-full border-2 border-white bg-emerald-500 shadow-md"></span>
            <div>
              <span class="text-[10px] text-emerald-400 font-bold uppercase tracking-wider block">Get Off At</span>
              <p class="text-xs font-bold text-white">${leg.alight_stop.name}</p>
              <span class="text-[11px] text-slate-400 font-mono">Arrives: ${leg.alight_time_formatted}</span>
            </div>
          </div>

        </div>

        <!-- Live Track Action -->
        ${trackBtnHtml}

      </div>
    `;
  }).join("");

  container.innerHTML = `
    <!-- Options Switcher -->
    <div class="space-y-1.5">
      <span class="text-xs font-bold uppercase tracking-wider text-slate-400 px-1">Available Trips</span>
      <div class="flex space-x-2">
        ${optionsPillsHtml}
      </div>
    </div>

    <!-- Summary Header -->
    <div class="bg-gradient-to-br from-indigo-950/80 to-slate-900 border border-indigo-500/30 rounded-2xl p-4 space-y-2.5 shadow-xl">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[10px] text-indigo-300 uppercase font-bold tracking-wider">Fastest Journey</span>
          <h3 class="text-xl font-black text-white">${currentOpt.departure_time} → ${currentOpt.arrival_time}</h3>
        </div>
        <div class="text-right">
          <span class="px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-300 font-bold text-xs border border-indigo-500/30">
            ${currentOpt.total_duration_mins} mins total
          </span>
          <p class="text-[11px] text-slate-400 mt-1">${currentOpt.bus_transfers === 0 ? 'Direct Ride (No Transfers)' : `${currentOpt.bus_transfers} bus transfer`}</p>
        </div>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-slate-800/80 text-[11px] text-slate-400">
        <span class="flex items-center space-x-1.5 text-emerald-400 font-medium">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Live GPS Tracking Ready</span>
        </span>
        <span class="text-slate-400 mono">Computed in ${currentRouteData.engine_latency_ms} ms</span>
      </div>
    </div>

    <!-- Step by Step Legs -->
    <div class="space-y-2.5 pt-1">
      <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 px-1">How to Get There</h4>
      ${legsHtml}
    </div>
  `;

  lucide.createIcons();
  drawRouteGeometry(currentOpt.itinerary);
}

function drawRouteGeometry(itinerary) {
  routePolylineLayer.clearLayers();
  const allCoords = [];

  itinerary.forEach(leg => {
    if (leg.geometry && leg.geometry.length > 0) {
      if (leg.is_walking) {
        const line = L.polyline(leg.geometry, {
          color: "#06b6d4",
          weight: 4,
          dashArray: "6, 8",
          opacity: 0.85
        });
        routePolylineLayer.addLayer(line);
      } else {
        const line = L.polyline(leg.geometry, {
          color: leg.route_color || "#4f46e5",
          weight: 6,
          opacity: 0.9,
          lineCap: "round",
          lineJoin: "round"
        });
        routePolylineLayer.addLayer(line);
      }
      allCoords.push(...leg.geometry);
    }
  });

  if (allCoords.length > 0) {
    map.fitBounds(L.latLngBounds(allCoords), { padding: [60, 60] });
  }
}

// Live Bus Tracking Mode
function trackBus(vehicleId, busNumber, boardLat, boardLon, busTitle) {
  trackedVehicleId = vehicleId;
  trackedBoardStop = { lat: boardLat, lon: boardLon };

  const hud = document.getElementById("tracking-hud");
  document.getElementById("hud-bus-pill").innerText = `BUS ${busNumber}`;
  document.getElementById("hud-bus-title").innerText = busTitle || `Bus ${busNumber}`;
  document.getElementById("hud-bus-id").innerText = `Vehicle ${vehicleId}`;
  hud.classList.remove("hidden");

  // Focus map on the bus
  const marker = busMarkers[vehicleId];
  if (marker) {
    map.flyTo(marker.getLatLng(), 16, { duration: 1.0 });
    marker.openPopup();
  }

  updateTrackedBusDisplay();
}

function stopTrackingBus() {
  trackedVehicleId = null;
  trackedBoardStop = null;
  document.getElementById("tracking-hud").classList.add("hidden");
  trackingPolylineLayer.clearLayers();
}

function updateTrackedBusDisplay() {
  if (!trackedVehicleId || !trackedBoardStop) return;

  const marker = busMarkers[trackedVehicleId];
  if (!marker) return;

  const busLatLng = marker.getLatLng();
  const d_lat = (busLatLng.lat - trackedBoardStop.lat) * 111320;
  const d_lon = (busLatLng.lng - trackedBoardStop.lon) * 111320 * Math.cos(trackedBoardStop.lat * Math.PI / 180);
  const distM = Math.round(Math.sqrt(d_lat*d_lat + d_lon*d_lon));
  const etaMins = Math.max(1, Math.round(distM / 9.5 / 60)); // ~35 km/h

  document.getElementById("hud-dist").innerText = distM > 1000 ? `${(distM/1000).toFixed(1)} km` : `${distM}m`;
  document.getElementById("hud-eta").innerText = `~${etaMins} min`;

  // Draw connecting dashed path from bus to boarding stop
  trackingPolylineLayer.clearLayers();
  const trail = L.polyline([[busLatLng.lat, busLatLng.lng], [trackedBoardStop.lat, trackedBoardStop.lon]], {
    color: "#38bdf8",
    weight: 3,
    dashArray: "4, 6",
    opacity: 0.9
  });
  trackingPolylineLayer.addLayer(trail);
}

// Real-Time WebSocket Telemetry
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      document.getElementById("live-telemetry-badge").classList.remove("hidden");
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "VEHICLE_POSITIONS" || data.type === "SNAPSHOT") {
        updateLiveVehicles(data.vehicles);
      }
    };

    ws.onclose = () => {
      setTimeout(initWebSocket, 3000);
    };
  } catch (e) {
    console.error("WS error:", e);
  }
}

function updateLiveVehicles(vehicles) {
  if (!vehicles) return;

  document.getElementById("fleet-count").innerText = vehicles.length;
  document.getElementById("telemetry-status-text").innerText = `${vehicles.length} Live Buses Moving`;

  if (vehicles.length > 0) {
    const v = vehicles[Math.floor(Math.random() * vehicles.length)];
    const delayText = v.delay_sec > 0 ? `(+${Math.round(v.delay_sec/60)}m delay)` : "on time";
    document.getElementById("live-ticker-text").innerText = 
      `Bus ${v.route_id} en route to ${v.to_stop} at ${Math.round(v.speed_kmh)} km/h • ${delayText}`;
  }

  vehicles.forEach(v => {
    const vid = v.vehicle_id;
    const isTracked = (vid === trackedVehicleId);

    if (!busMarkers[vid]) {
      const icon = L.divIcon({
        className: "bus-marker-wrapper",
        html: `
          <div class="bus-marker ${isTracked ? 'tracked' : ''}" style="background-color: ${v.route_color};">
            <div class="bus-pulse"></div>
            <i data-lucide="bus" style="width: 16px; height: 16px;"></i>
          </div>
        `,
        iconSize: [34, 34],
        iconAnchor: [17, 17]
      });

      const marker = L.marker([v.lat, v.lon], { icon }).addTo(map);
      marker.bindPopup(`
        <div class="p-2 space-y-1 text-slate-900 font-sans">
          <div class="flex items-center space-x-2">
            <span class="px-2 py-0.5 rounded text-xs font-bold text-white" style="background: ${v.route_color}">Bus ${v.route_id}</span>
            <h4 class="font-bold text-sm">${v.vehicle_id}</h4>
          </div>
          <p class="text-xs text-slate-600">Heading towards: <strong>${v.to_stop}</strong></p>
          <div class="flex items-center justify-between text-xs pt-1 border-t">
            <span>Speed: ${Math.round(v.speed_kmh)} km/h</span>
            <span class="font-bold ${v.delay_sec > 60 ? 'text-rose-600' : 'text-emerald-600'}">
              ${v.delay_sec > 60 ? `+${Math.round(v.delay_sec/60)}m late` : 'On Time'}
            </span>
          </div>
        </div>
      `);
      busMarkers[vid] = marker;
      lucide.createIcons();
    } else {
      busMarkers[vid].setLatLng([v.lat, v.lon]);
    }
  });

  if (trackedVehicleId) {
    updateTrackedBusDisplay();
  }

  renderFleetList(vehicles);
}

function renderFleetList(vehicles) {
  const container = document.getElementById("fleet-list-container");
  if (!container || container.offsetParent === null) return;

  container.innerHTML = vehicles.map(v => `
    <div class="bg-slate-900 border border-slate-800 p-3.5 rounded-2xl space-y-2 hover:border-indigo-500/50 transition cursor-pointer shadow"
         onclick="focusVehicle('${v.vehicle_id}')">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2.5">
          <span class="px-2.5 py-0.5 rounded-lg text-xs font-black text-white shadow" style="background-color: ${v.route_color}">
            BUS ${v.route_id}
          </span>
          <span class="text-xs font-bold text-white">${v.vehicle_id}</span>
        </div>
        <span class="text-[11px] font-semibold ${v.delay_sec > 60 ? 'text-rose-400' : 'text-emerald-400'}">
          ${v.delay_sec > 60 ? `+${Math.round(v.delay_sec/60)}m late` : 'On Time'}
        </span>
      </div>

      <div class="text-xs text-slate-400 flex items-center justify-between">
        <span class="truncate mr-2">Towards: <strong class="text-slate-200">${v.to_stop}</strong></span>
        <span class="mono shrink-0">${Math.round(v.speed_kmh)} km/h</span>
      </div>
    </div>
  `).join("");
}

function focusVehicle(vid) {
  const marker = busMarkers[vid];
  if (marker) {
    map.flyTo(marker.getLatLng(), 16, { duration: 1.0 });
    marker.openPopup();
  }
}

// Departures Modal
async function openDeparturesModal(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (!stop) return;

  document.getElementById("modal-stop-name").innerText = stop.name;
  document.getElementById("modal-stop-id").innerText = `Stop #${stop.id}`;
  const list = document.getElementById("modal-departures-list");
  list.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">Loading scheduled buses...</div>`;

  document.getElementById("departures-modal").classList.remove("hidden");

  try {
    const res = await fetch(`/api/stops/${stopId}/departures`);
    const data = await res.json();
    if (!data.departures || data.departures.length === 0) {
      list.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">No scheduled departures in next 2 hours.</div>`;
      return;
    }

    list.innerHTML = data.departures.map(d => `
      <div class="bg-slate-950 border border-slate-800 p-3 rounded-xl flex items-center justify-between">
        <div class="flex items-center space-x-3">
          <span class="px-2.5 py-1 rounded-lg text-xs font-black text-white shadow" style="background-color: ${d.route_color || '#4F46E5'}">
            BUS ${d.route_id || 'Transit'}
          </span>
          <div>
            <p class="text-xs font-bold text-white">${d.headsign || d.bus_name}</p>
            <span class="text-[10px] text-slate-400 font-mono">Departs at ${d.departure_time}</span>
          </div>
        </div>
        <span class="px-2.5 py-1 rounded-full text-xs font-semibold ${d.delay_sec > 0 ? 'bg-amber-500/10 text-amber-400' : 'bg-emerald-500/10 text-emerald-400'}">
          ${d.delay_sec > 0 ? `+${Math.round(d.delay_sec/60)}m delay` : 'On Schedule'}
        </span>
      </div>
    `).join("");
  } catch (err) {
    list.innerHTML = `<div class="p-4 text-center text-xs text-rose-500">Error loading departures.</div>`;
  }
}

function closeDeparturesModal() {
  document.getElementById("departures-modal").classList.add("hidden");
}

// Tab Switching
function switchTab(tabId) {
  ["planner", "fleet", "metrics"].forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    const btn = document.getElementById(`tab-${t}-btn`);
    if (t === tabId) {
      el.classList.remove("hidden");
      btn.classList.add("border-indigo-500", "text-indigo-400");
      btn.classList.remove("border-transparent", "text-slate-400");
    } else {
      el.classList.add("hidden");
      btn.classList.remove("border-indigo-500", "text-indigo-400");
      btn.classList.add("border-transparent", "text-slate-400");
    }
  });
}

function updateClock() {
  const now = new Date();
  document.getElementById("live-clock").innerText = now.toTimeString().split(' ')[0];
}
