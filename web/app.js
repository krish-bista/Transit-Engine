// Global State
let map;
let stopsData = [];
let routesData = [];
let sourceStopId = 217; // Edward & Gordon
let targetStopId = 184; // Thunder Bay Regional Hospital
let busMarkers = {};
let routePolylineLayer = null;
let stopMarkersLayer = null;
let showStopPins = true;
let currentRouteData = null;
let selectedOptionIndex = 0;
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
    document.getElementById("source-id-tag").innerText = `ID: ${sStop.id}`;
  }
  if (tStop) {
    document.getElementById("target-input").value = tStop.name;
    document.getElementById("target-id-tag").innerText = `ID: ${tStop.id}`;
  }

  setupAutocomplete("source-input", "source-results", (stop) => {
    sourceStopId = stop.id;
    document.getElementById("source-id-tag").innerText = `ID: ${stop.id}`;
    highlightStopOnMap(stop);
  });

  setupAutocomplete("target-input", "target-results", (stop) => {
    targetStopId = stop.id;
    document.getElementById("target-id-tag").innerText = `ID: ${stop.id}`;
    highlightStopOnMap(stop);
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
}

function centerMapOnTransit() {
  if (map) {
    map.setView([48.416, -89.236], 13);
  }
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
    const icon = L.divIcon({
      className: "stop-pin-wrapper",
      html: `<div class="stop-pin" title="${stop.name}"></div>`,
      iconSize: [10, 10],
      iconAnchor: [5, 5]
    });

    const marker = L.marker([stop.lat, stop.lon], { icon });
    marker.bindPopup(`
      <div class="p-2 space-y-1.5 text-slate-900 font-sans">
        <h4 class="font-bold text-sm">${stop.name}</h4>
        <span class="text-xs text-slate-500 font-mono">Stop ID: ${stop.id} (${stop.raw_id})</span>
        <div class="flex space-x-2 pt-2">
          <button onclick="setAsOrigin(${stop.id})" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-xs font-semibold">Origin</button>
          <button onclick="setAsDestination(${stop.id})" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded text-xs font-semibold">Destination</button>
          <button onclick="openDeparturesModal(${stop.id})" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold">Schedule</button>
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
    document.getElementById("source-id-tag").innerText = `ID: ${stop.id}`;
    map.closePopup();
  }
}

function setAsDestination(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (stop) {
    targetStopId = stop.id;
    document.getElementById("target-input").value = stop.name;
    document.getElementById("target-id-tag").innerText = `ID: ${stop.id}`;
    map.closePopup();
  }
}

function highlightStopOnMap(stop) {
  if (map && stop.lat && stop.lon) {
    map.flyTo([stop.lat, stop.lon], 15, { duration: 1.0 });
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
      results.innerHTML = `<div class="p-3 text-xs text-slate-500">No stops found</div>`;
      results.classList.remove("hidden");
      return;
    }

    results.innerHTML = matches.map(s => `
      <div class="p-2.5 hover:bg-slate-800 cursor-pointer border-b border-slate-800/50 flex items-center justify-between transition"
           onclick="selectStop('${inputId}', '${resultsId}', ${s.id})">
        <div>
          <p class="text-sm font-medium text-slate-200">${s.name}</p>
          <span class="text-[10px] text-slate-500 font-mono">ID: ${s.id}</span>
        </div>
        <span class="text-xs text-indigo-400">Select</span>
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
      document.getElementById("source-id-tag").innerText = `ID: ${stop.id}`;
    } else {
      targetStopId = stop.id;
      document.getElementById("target-id-tag").innerText = `ID: ${stop.id}`;
    }
    highlightStopOnMap(stop);
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
  document.getElementById("source-id-tag").innerText = `ID: ${sourceStopId}`;
  document.getElementById("target-id-tag").innerText = `ID: ${targetStopId}`;
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

// Calculate Route with Multi-Modal Range-RAPTOR
async function calculateRoute() {
  const btn = document.getElementById("search-route-btn");
  const container = document.getElementById("route-results-container");
  const depTime = document.getElementById("departure-time").value || "08:47";
  const depDate = document.getElementById("departure-date").value || "tomorrow";

  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-white"></i><span>Routing Multi-Modal Arcs...</span>`;
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
    btn.innerHTML = `<i data-lucide="zap" class="w-4 h-4 text-amber-300"></i><span>Calculate Multi-Modal Routes</span>`;
    lucide.createIcons();

    if (!data.success || !data.options || data.options.length === 0) {
      container.innerHTML = `
        <div class="bg-amber-950/30 border border-amber-500/30 p-4 rounded-xl text-amber-300 text-xs space-y-1">
          <p class="font-bold">No Connections Found</p>
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
    btn.innerHTML = `<i data-lucide="zap" class="w-4 h-4 text-amber-300"></i><span>Calculate Multi-Modal Routes</span>`;
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
        <span class="text-[10px] text-slate-500">${opt.bus_transfers === 0 ? 'Direct Bus' : `${opt.bus_transfers} bus transfer`}</span>
      </button>
    `;
  }).join("");

  // Step-by-Step Legs
  const legsHtml = currentOpt.itinerary.map(leg => {
    if (leg.is_walking) {
      return `
        <div class="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3 flex items-center space-x-3">
          <div class="w-8 h-8 rounded-lg bg-slate-800 text-slate-300 flex items-center justify-center shrink-0">
            <i data-lucide="footprints" class="w-4 h-4 text-cyan-400"></i>
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

    return `
      <div class="leg-card bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-2.5">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="px-2 py-0.5 rounded-md text-xs font-bold shadow text-white"
                  style="background-color: ${leg.route_color}">
              R-${leg.route_short_name}
            </span>
            <span class="text-xs font-bold text-white">Route ${leg.route_short_name}</span>
          </div>
          <span class="text-xs text-indigo-400 font-mono font-semibold">${leg.duration_mins} min</span>
        </div>

        <div class="relative pl-5 space-y-3 border-l-2 border-slate-700 ml-2 py-0.5">
          <div class="relative">
            <span class="absolute -left-[27px] top-1 w-3 h-3 rounded-full border-2 border-indigo-500 bg-slate-950"></span>
            <div class="flex items-center justify-between">
              <p class="text-xs font-semibold text-slate-200 truncate mr-2">${leg.board_stop.name}</p>
              <span class="text-xs text-slate-400 font-mono shrink-0">${leg.board_time_formatted}</span>
            </div>
          </div>

          <div class="relative">
            <span class="absolute -left-[27px] top-1 w-3 h-3 rounded-full border-2 border-emerald-500 bg-emerald-500"></span>
            <div class="flex items-center justify-between">
              <p class="text-xs font-semibold text-slate-200 truncate mr-2">${leg.alight_stop.name}</p>
              <span class="text-xs text-slate-400 font-mono shrink-0">${leg.alight_time_formatted}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <!-- Options Switcher -->
    <div class="space-y-1.5">
      <span class="text-xs font-bold uppercase tracking-wider text-slate-400 px-1">Upcoming Departures</span>
      <div class="flex space-x-2">
        ${optionsPillsHtml}
      </div>
    </div>

    <!-- Summary Header -->
    <div class="bg-gradient-to-br from-indigo-950/70 to-slate-900 border border-indigo-500/30 rounded-2xl p-4 space-y-2.5">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[11px] text-indigo-300 uppercase font-bold tracking-wider">Scheduled Journey</span>
          <h3 class="text-xl font-black text-white">${currentOpt.departure_time} → ${currentOpt.arrival_time}</h3>
        </div>
        <div class="text-right">
          <span class="px-2.5 py-1 rounded-full bg-indigo-500/20 text-indigo-300 font-bold text-xs">
            ${currentOpt.total_duration_mins} mins
          </span>
          <p class="text-[10px] text-slate-400 mt-1">${currentOpt.bus_transfers === 0 ? 'Direct Bus' : `${currentOpt.bus_transfers} bus transfer(s)`}</p>
        </div>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-slate-800/80 text-[11px] text-slate-400">
        <span class="flex items-center space-x-1">
          <i data-lucide="cpu" class="w-3.5 h-3.5 text-cyan-400"></i>
          <span>C++ McRAPTOR Query: <strong class="text-white mono">${currentRouteData.engine_latency_ms} ms</strong></span>
        </span>
        <span class="text-emerald-400 font-medium flex items-center space-x-1">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          <span>Footpaths Enabled</span>
        </span>
      </div>
    </div>

    <!-- Step by Step Legs -->
    <div class="space-y-2 pt-1">
      <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 px-1">Step-by-Step Directions</h4>
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
        // Dashed polyline for walking legs
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
    map.fitBounds(L.latLngBounds(allCoords), { padding: [50, 50] });
  }
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
  document.getElementById("telemetry-status-text").innerText = `Connected: ${vehicles.length} Live Buses`;

  if (vehicles.length > 0) {
    const v = vehicles[Math.floor(Math.random() * vehicles.length)];
    const delayText = v.delay_sec > 0 ? `(+${Math.round(v.delay_sec/60)}m delay)` : "on time";
    document.getElementById("live-ticker-text").innerText = 
      `${v.vehicle_id} (Route ${v.route_id}) en route to ${v.to_stop} at ${Math.round(v.speed_kmh)} km/h • ${delayText}`;
  }

  vehicles.forEach(v => {
    const vid = v.vehicle_id;
    if (!busMarkers[vid]) {
      const icon = L.divIcon({
        className: "bus-marker-wrapper",
        html: `
          <div class="bus-marker" style="background-color: ${v.route_color};">
            <div class="bus-pulse"></div>
            <i data-lucide="bus" style="width: 16px; height: 16px;"></i>
          </div>
        `,
        iconSize: [32, 32],
        iconAnchor: [16, 16]
      });

      const marker = L.marker([v.lat, v.lon], { icon }).addTo(map);
      marker.bindPopup(`
        <div class="p-2 space-y-1 text-slate-900 font-sans">
          <div class="flex items-center space-x-2">
            <span class="px-2 py-0.5 rounded text-xs font-bold text-white" style="background: ${v.route_color}">R-${v.route_id}</span>
            <h4 class="font-bold text-sm">${v.vehicle_id}</h4>
          </div>
          <p class="text-xs text-slate-600">Next: <strong>${v.to_stop}</strong></p>
          <div class="flex items-center justify-between text-xs pt-1 border-t">
            <span>Speed: ${Math.round(v.speed_kmh)} km/h</span>
            <span class="font-bold ${v.delay_sec > 60 ? 'text-rose-600' : 'text-emerald-600'}">
              ${v.delay_sec > 60 ? `+${Math.round(v.delay_sec/60)}m delay` : 'On Schedule'}
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

  renderFleetList(vehicles);
}

function renderFleetList(vehicles) {
  const container = document.getElementById("fleet-list-container");
  if (!container || container.offsetParent === null) return;

  container.innerHTML = vehicles.map(v => `
    <div class="bg-slate-900 border border-slate-800 p-3 rounded-xl space-y-2 hover:border-slate-700 transition cursor-pointer"
         onclick="focusVehicle('${v.vehicle_id}')">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="px-2 py-0.5 rounded text-xs font-bold text-white shadow" style="background-color: ${v.route_color}">
            ${v.route_id}
          </span>
          <span class="text-xs font-bold text-white">${v.vehicle_id}</span>
        </div>
        <span class="text-[11px] font-semibold ${v.delay_sec > 60 ? 'text-rose-400' : 'text-emerald-400'}">
          ${v.delay_sec > 60 ? `+${Math.round(v.delay_sec/60)}m late` : 'On Time'}
        </span>
      </div>

      <div class="text-[11px] text-slate-400 flex items-center justify-between">
        <span>Towards: <strong class="text-slate-300">${v.to_stop}</strong></span>
        <span class="mono">${Math.round(v.speed_kmh)} km/h</span>
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
  document.getElementById("modal-stop-id").innerText = `Stop ID: ${stop.id} (${stop.raw_id})`;
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
          <div class="w-8 h-8 rounded-lg bg-indigo-600/20 text-indigo-400 flex items-center justify-center font-bold text-xs">
            BUS
          </div>
          <div>
            <p class="text-xs font-bold text-white font-mono">${d.departure_time}</p>
            <span class="text-[10px] text-slate-500">Trip: ${d.trip_id.slice(-8)}</span>
          </div>
        </div>
        <span class="px-2.5 py-1 rounded-full text-xs font-semibold ${d.delay_sec > 0 ? 'bg-amber-500/10 text-amber-400' : 'bg-emerald-500/10 text-emerald-400'}">
          ${d.delay_sec > 0 ? `+${Math.round(d.delay_sec/60)}m delay` : 'On Time'}
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
