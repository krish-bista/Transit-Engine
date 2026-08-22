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
let isJourneyActive = false;
let trackedVehicleId = null;
let trackedBoardStop = null;
let ws;

// Initialize when DOM loads
document.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  initMap();
  updateClock();
  setInterval(updateClock, 1000);

  await loadStops();
  await loadRoutes();
  initWebSocket();

  // Set default names in inputs
  const sStop = stopsData.find(s => s.id === sourceStopId);
  const tStop = stopsData.find(s => s.id === targetStopId);
  const sInput = document.getElementById("source-input");
  const tInput = document.getElementById("target-input");
  if (sInput && sStop) sInput.value = sStop.name;
  if (tInput && tStop) tInput.value = tStop.name;

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
  if (input) input.value = "Locating your position...";

  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    if (input) input.value = "Edward & Gordon";
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
        if (input) input.value = `${nearest.name} (Near You)`;
        highlightStopOnMap(nearest, true);
        calculateRoute();
      } catch (err) {
        if (input) input.value = "Edward & Gordon";
        sourceStopId = 217;
      }
    },
    (err) => {
      if (input) input.value = "Edward & Gordon";
      sourceStopId = 217;
      calculateRoute();
    },
    { timeout: 6000 }
  );
}

function setQuickDestination(name, stopId) {
  targetStopId = stopId;
  const input = document.getElementById("target-input");
  if (input) input.value = name;
  switchTab('planner');
  renderStopPins();
  calculateRoute();
}

// Load Stops from Gateway
async function loadStops() {
  try {
    const res = await fetch("/api/stops");
    if (!res.ok) throw new Error("Failed to fetch stops");
    stopsData = await res.json();
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
  if (!stopMarkersLayer) return;
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
        <div class="flex space-x-2 pt-2">
          <button onclick="setAsOrigin(${stop.id})" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-xs font-semibold">Start Here</button>
          <button onclick="setAsDestination(${stop.id})" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded text-xs font-semibold">Go Here</button>
          <button onclick="openDeparturesModal(${stop.id})" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold">Buses</button>
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
  if (btn) {
    btn.classList.toggle("text-slate-400", !showStopPins);
    btn.classList.toggle("text-indigo-400", showStopPins);
  }
}

function setAsOrigin(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (stop) {
    sourceStopId = stop.id;
    const input = document.getElementById("source-input");
    if (input) input.value = stop.name;
    map.closePopup();
    renderStopPins();
    calculateRoute();
  }
}

function setAsDestination(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (stop) {
    targetStopId = stop.id;
    const input = document.getElementById("target-input");
    if (input) input.value = stop.name;
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
  if (!input || !results) return;

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
    const input = document.getElementById(inputId);
    const results = document.getElementById(resultsId);
    if (input) input.value = stop.name;
    if (results) results.classList.add("hidden");
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

  const sInput = document.getElementById("source-input");
  const tInput = document.getElementById("target-input");
  if (sInput) sInput.value = sStop ? sStop.name : "";
  if (tInput) tInput.value = tStop ? tStop.name : "";

  renderStopPins();
  calculateRoute();
}

function setTimePreset(timeStr) {
  const input = document.getElementById("departure-time");
  if (input) input.value = timeStr;
  calculateRoute();
}

function setNowTime() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const input = document.getElementById("departure-time");
  if (input) input.value = `${h}:${m}`;
  calculateRoute();
}

// Calculate Route
async function calculateRoute() {
  const btn = document.getElementById("search-route-btn");
  const container = document.getElementById("route-results-container");
  const timeInput = document.getElementById("departure-time");
  const dateInput = document.getElementById("departure-date");

  const depTime = (timeInput && timeInput.value) ? timeInput.value : "08:47";
  const depDate = (dateInput && dateInput.value) ? dateInput.value : "tomorrow";

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-white"></i><span>Finding Buses...</span>`;
    if (window.lucide) lucide.createIcons();
  }

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
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="compass" class="w-4 h-4 text-white"></i><span>Find Best Bus Routes</span>`;
      if (window.lucide) lucide.createIcons();
    }

    if (!data.success || !data.options || data.options.length === 0) {
      if (container) {
        container.innerHTML = `
          <div class="bg-amber-950/30 border border-amber-500/30 p-4 rounded-xl text-amber-300 text-xs space-y-1">
            <p class="font-bold">No Bus Connections Found</p>
            <p>${data.message || "Try picking another departure time or nearby stops."}</p>
          </div>
        `;
      }
      if (routePolylineLayer) routePolylineLayer.clearLayers();
      return;
    }

    currentRouteData = data;
    selectedOptionIndex = 0;
    isJourneyActive = false;

    renderOptionsList();

  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="compass" class="w-4 h-4 text-white"></i><span>Find Best Bus Routes</span>`;
      if (window.lucide) lucide.createIcons();
    }
    if (container) {
      container.innerHTML = `
        <div class="bg-rose-950/30 border border-rose-500/30 p-4 rounded-xl text-rose-300 text-xs">
          <p class="font-bold">Routing Error</p>
          <p>${err.message}</p>
        </div>
      `;
    }
  }
}

// 1. Render Options List (User-friendly cards with "GO" button)
function renderOptionsList() {
  if (!currentRouteData || !currentRouteData.options) return;
  const container = document.getElementById("route-results-container");
  if (!container) return;

  const options = currentRouteData.options;

  const cardsHtml = options.map((opt, idx) => {
    // Collect bus pills for summary
    const busPills = opt.itinerary.filter(l => !l.is_walking).map(l => `
      <span class="px-2.5 py-0.5 rounded-lg text-xs font-black text-white shadow" style="background-color: ${l.route_color}">
        ${l.bus_name || `BUS ${l.bus_number}`}
      </span>
    `).join("<span class='text-slate-500 text-xs font-bold'>→</span>");

    const totalWalkMins = opt.itinerary.filter(l => l.is_walking).reduce((sum, l) => sum + l.duration_mins, 0);
    const isFirst = (idx === 0);

    return `
      <div class="bg-slate-900 border ${isFirst ? 'border-indigo-500/60 shadow-indigo-500/10' : 'border-slate-800'} hover:border-indigo-500 rounded-2xl p-4 space-y-3.5 transition shadow-xl cursor-pointer"
           onclick="startJourney(${idx})">
        
        <!-- Header -->
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="px-2.5 py-1 rounded-full text-xs font-bold ${isFirst ? 'bg-indigo-500 text-white' : 'bg-slate-800 text-slate-300'}">
              ${isFirst ? '🌟 Recommended' : `Option ${idx + 1}`}
            </span>
            <span class="text-xs font-bold text-slate-400">${opt.bus_transfers === 0 ? 'Direct Ride' : `${opt.bus_transfers} Transfer`}</span>
          </div>
          <span class="text-lg font-black text-cyan-400">${opt.total_duration_mins} min</span>
        </div>

        <!-- Times & Bus Lines -->
        <div class="flex items-center justify-between border-y border-slate-800/80 py-2.5">
          <div>
            <h4 class="text-base font-bold text-white">${opt.departure_time} → ${opt.arrival_time}</h4>
            <span class="text-xs text-slate-400 flex items-center space-x-1 mt-0.5">
              <i data-lucide="footprints" class="w-3.5 h-3.5 text-slate-500"></i>
              <span>${totalWalkMins} min walking</span>
            </span>
          </div>

          <div class="flex items-center space-x-1.5 flex-wrap justify-end gap-1">
            ${busPills || "<span class='text-xs text-cyan-400 font-bold'>Walk</span>"}
          </div>
        </div>

        <!-- GO Button -->
        <button onclick="event.stopPropagation(); startJourney(${idx})"
                class="w-full py-2.5 px-4 bg-gradient-to-r from-indigo-600 to-cyan-500 hover:from-indigo-500 hover:to-cyan-400 text-white font-black text-sm rounded-xl shadow-lg flex items-center justify-center space-x-2 transition">
          <span>🚀 GO • View Step-by-Step Directions</span>
        </button>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="flex items-center justify-between px-1">
      <span class="text-xs font-bold uppercase tracking-wider text-slate-400">Available Options</span>
      <span class="text-xs text-emerald-400 font-medium">${options.length} routes found</span>
    </div>
    <div class="space-y-3">
      ${cardsHtml}
    </div>
  `;

  if (window.lucide) lucide.createIcons();
  if (options[0]) drawRouteGeometry(options[0].itinerary);
}

// 2. Active Step-by-Step Personalized Journey Mode
function startJourney(optionIndex) {
  selectedOptionIndex = optionIndex;
  isJourneyActive = true;

  const container = document.getElementById("route-results-container");
  if (!container || !currentRouteData || !currentRouteData.options) return;

  const opt = currentRouteData.options[optionIndex];

  // Find first bus to track
  const firstBusLeg = opt.itinerary.find(l => !l.is_walking);
  if (firstBusLeg && firstBusLeg.live_vehicle) {
    trackBus(firstBusLeg.live_vehicle.vehicle_id, firstBusLeg.bus_number, firstBusLeg.board_stop.lat, firstBusLeg.board_stop.lon, firstBusLeg.bus_name);
  }

  const legsHtml = opt.itinerary.map((leg, i) => {
    if (leg.is_walking) {
      return `
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-3.5 flex items-center space-x-3.5">
          <div class="w-10 h-10 rounded-xl bg-cyan-950/80 border border-cyan-500/30 text-cyan-400 flex items-center justify-center shrink-0">
            <i data-lucide="footprints" class="w-5 h-5"></i>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between">
              <h5 class="text-sm font-bold text-white">${leg.action_title}</h5>
              <span class="text-xs font-bold text-cyan-400">${leg.duration_mins} min</span>
            </div>
            <p class="text-xs text-slate-400 mt-0.5">${leg.distance_m}m walk • Leave at ${leg.board_time_formatted}</p>
          </div>
        </div>
      `;
    }

    const liveVeh = leg.live_vehicle;
    return `
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3.5 shadow-xl">
        
        <!-- Header: Exact Bus Line & Destination -->
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center space-x-2.5">
            <span class="px-3 py-1.5 rounded-xl text-sm font-black text-white shadow-lg flex items-center space-x-1"
                  style="background-color: ${leg.route_color}">
              <i data-lucide="bus" class="w-4 h-4 mr-1"></i>
              <span>BUS ${leg.bus_number}</span>
            </span>
            <div>
              <h4 class="text-sm font-black text-white leading-tight">${leg.bus_name}</h4>
              <span class="text-xs text-emerald-400 font-semibold flex items-center space-x-1 mt-0.5">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>Scheduled at ${leg.board_time_formatted}</span>
              </span>
            </div>
          </div>
          <span class="text-xs font-black text-slate-300 bg-slate-800 px-2.5 py-1 rounded-lg mono">${leg.duration_mins} min</span>
        </div>

        <!-- Step Instructions -->
        <div class="relative pl-6 space-y-3 border-l-2 border-indigo-500/70 ml-3 py-1">
          
          <!-- Boarding Stop -->
          <div class="relative">
            <span class="absolute -left-[33px] top-1 w-4 h-4 rounded-full border-2 border-white bg-indigo-600 shadow-md"></span>
            <div>
              <span class="text-[10px] text-indigo-400 font-black uppercase tracking-wider block">Where to Board</span>
              <p class="text-sm font-bold text-white">${leg.board_stop.name}</p>
              <span class="text-xs text-slate-400">Boarding Time: <strong class="text-slate-200">${leg.board_time_formatted}</strong></span>
            </div>
          </div>

          <!-- Ride Summary -->
          <div class="text-xs text-slate-300 bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-800/80 flex items-center justify-between">
            <span class="font-medium">🚌 Stay on bus for <strong>${leg.stops_count} stops</strong> (~${leg.duration_mins} mins)</span>
          </div>

          <!-- Alighting Stop -->
          <div class="relative">
            <span class="absolute -left-[33px] top-1 w-4 h-4 rounded-full border-2 border-white bg-emerald-500 shadow-md"></span>
            <div>
              <span class="text-[10px] text-emerald-400 font-black uppercase tracking-wider block">Where to Get Off</span>
              <p class="text-sm font-bold text-white">${leg.alight_stop.name}</p>
              <span class="text-xs text-slate-400">Arrives at: <strong class="text-slate-200">${leg.alight_time_formatted}</strong></span>
            </div>
          </div>

        </div>

        <!-- Live Bus Button -->
        ${liveVeh ? `
          <button onclick="trackBus('${liveVeh.vehicle_id}', '${leg.bus_number}', ${leg.board_stop.lat}, ${leg.board_stop.lon}, '${leg.bus_name}')"
                  class="w-full py-2.5 px-3.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white font-bold text-xs rounded-xl shadow flex items-center justify-between transition">
            <span class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
              <span>Live Bus GPS (${liveVeh.distance_m}m away)</span>
            </span>
            <span class="text-cyan-400 font-mono">Arrives in ~${liveVeh.eta_mins}m →</span>
          </button>
        ` : ''}

      </div>
    `;
  }).join("");

  container.innerHTML = `
    <!-- Top Action Bar -->
    <div class="flex items-center justify-between pb-1">
      <button onclick="exitJourney()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-300 rounded-xl transition flex items-center space-x-1.5 border border-slate-700">
        <i data-lucide="arrow-left" class="w-4 h-4"></i>
        <span>All Options</span>
      </button>
      <span class="text-xs text-indigo-400 font-bold">Option ${optionIndex + 1} • ${opt.total_duration_mins} mins</span>
    </div>

    <!-- Active Summary Header -->
    <div class="bg-gradient-to-br from-indigo-950 to-slate-900 border border-indigo-500/40 rounded-2xl p-4 space-y-2 shadow-2xl">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[10px] text-indigo-300 uppercase font-black tracking-wider">Your Journey</span>
          <h3 class="text-xl font-black text-white">${opt.departure_time} → ${opt.arrival_time}</h3>
        </div>
        <div class="text-right">
          <span class="px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 font-bold text-xs border border-emerald-500/30">
            ${opt.total_duration_mins} mins
          </span>
          <p class="text-[11px] text-slate-400 mt-1">${opt.bus_transfers === 0 ? 'Direct Ride' : `${opt.bus_transfers} transfer`}</p>
        </div>
      </div>
    </div>

    <!-- Step by Step Directions -->
    <div class="space-y-3 pt-1">
      <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 px-1">Step-by-Step Directions</h4>
      ${legsHtml}
    </div>
  `;

  if (window.lucide) lucide.createIcons();
  drawRouteGeometry(opt.itinerary);
}

function exitJourney() {
  isJourneyActive = false;
  stopTrackingBus();
  renderOptionsList();
}

function drawRouteGeometry(itinerary) {
  if (!routePolylineLayer) return;
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

  if (allCoords.length > 0 && map) {
    map.fitBounds(L.latLngBounds(allCoords), { padding: [60, 60] });
  }
}

// Live Bus Tracking Mode
function trackBus(vehicleId, busNumber, boardLat, boardLon, busTitle) {
  trackedVehicleId = vehicleId;
  trackedBoardStop = { lat: boardLat, lon: boardLon };

  const hud = document.getElementById("tracking-hud");
  const pill = document.getElementById("hud-bus-pill");
  const title = document.getElementById("hud-bus-title");
  const idEl = document.getElementById("hud-bus-id");

  if (pill) pill.innerText = `BUS ${busNumber}`;
  if (title) title.innerText = busTitle || `Bus ${busNumber}`;
  if (idEl) idEl.innerText = `Approaching Your Stop`;
  if (hud) hud.classList.remove("hidden");

  // Focus map on the bus
  const marker = busMarkers[vehicleId];
  if (marker && map) {
    map.flyTo(marker.getLatLng(), 16, { duration: 1.0 });
    marker.openPopup();
  }

  updateTrackedBusDisplay();
}

function stopTrackingBus() {
  trackedVehicleId = null;
  trackedBoardStop = null;
  const hud = document.getElementById("tracking-hud");
  if (hud) hud.classList.add("hidden");
  if (trackingPolylineLayer) trackingPolylineLayer.clearLayers();
}

function updateTrackedBusDisplay() {
  if (!trackedVehicleId || !trackedBoardStop) return;

  const marker = busMarkers[trackedVehicleId];
  if (!marker) return;

  const busLatLng = marker.getLatLng();
  const d_lat = (busLatLng.lat - trackedBoardStop.lat) * 111320;
  const d_lon = (busLatLng.lng - trackedBoardStop.lon) * 111320 * Math.cos(trackedBoardStop.lat * Math.PI / 180);
  const distM = Math.round(Math.sqrt(d_lat*d_lat + d_lon*d_lon));
  const etaMins = Math.max(1, Math.round(distM / 9.5 / 60));

  const distEl = document.getElementById("hud-dist");
  const etaEl = document.getElementById("hud-eta");
  if (distEl) distEl.innerText = distM > 1000 ? `${(distM/1000).toFixed(1)} km` : `${distM}m`;
  if (etaEl) etaEl.innerText = `~${etaMins} min`;

  if (trackingPolylineLayer) {
    trackingPolylineLayer.clearLayers();
    const trail = L.polyline([[busLatLng.lat, busLatLng.lng], [trackedBoardStop.lat, trackedBoardStop.lon]], {
      color: "#38bdf8",
      weight: 3,
      dashArray: "4, 6",
      opacity: 0.9
    });
    trackingPolylineLayer.addLayer(trail);
  }
}

// Real-Time WebSocket Telemetry
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      const badge = document.getElementById("live-telemetry-badge");
      if (badge) badge.classList.remove("hidden");
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

  const fleetCount = document.getElementById("fleet-count");
  const telemetryText = document.getElementById("telemetry-status-text");
  const tickerText = document.getElementById("live-ticker-text");

  if (fleetCount) fleetCount.innerText = vehicles.length;
  if (telemetryText) telemetryText.innerText = `${vehicles.length} Live Buses on Roads`;

  if (vehicles.length > 0 && tickerText) {
    const v = vehicles[Math.floor(Math.random() * vehicles.length)];
    const delayText = v.delay_sec > 0 ? `(+${Math.round(v.delay_sec/60)}m delay)` : "on time";
    tickerText.innerText = 
      `${v.bus_name || `Bus ${v.route_id}`} en route to ${v.to_stop} at ${Math.round(v.speed_kmh)} km/h • ${delayText}`;
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
            <span class="px-2 py-0.5 rounded text-xs font-bold text-white" style="background: ${v.route_color}">${v.bus_name || `Bus ${v.route_id}`}</span>
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
      if (window.lucide) lucide.createIcons();
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
            ${v.bus_name || `BUS ${v.route_id}`}
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
  if (marker && map) {
    map.flyTo(marker.getLatLng(), 16, { duration: 1.0 });
    marker.openPopup();
  }
}

// Departures Modal
async function openDeparturesModal(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (!stop) return;

  const stopNameEl = document.getElementById("modal-stop-name");
  const stopIdEl = document.getElementById("modal-stop-id");
  const list = document.getElementById("modal-departures-list");
  const modal = document.getElementById("departures-modal");

  if (stopNameEl) stopNameEl.innerText = stop.name;
  if (stopIdEl) stopIdEl.innerText = `Stop Schedule`;
  if (list) list.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">Loading scheduled buses...</div>`;
  if (modal) modal.classList.remove("hidden");

  try {
    const res = await fetch(`/api/stops/${stopId}/departures`);
    const data = await res.json();
    if (!data.departures || data.departures.length === 0) {
      if (list) list.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">No scheduled departures in next 2 hours.</div>`;
      return;
    }

    if (list) {
      list.innerHTML = data.departures.map(d => `
        <div class="bg-slate-950 border border-slate-800 p-3 rounded-xl flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <span class="px-2.5 py-1 rounded-lg text-xs font-black text-white shadow" style="background-color: ${d.route_color || '#4F46E5'}">
              ${d.bus_name || `BUS ${d.route_id}`}
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
    }
  } catch (err) {
    if (list) list.innerHTML = `<div class="p-4 text-center text-xs text-rose-500">Error loading departures.</div>`;
  }
}

function closeDeparturesModal() {
  const modal = document.getElementById("departures-modal");
  if (modal) modal.classList.add("hidden");
}

// Tab Switching
function switchTab(tabId) {
  ["planner", "fleet", "places"].forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    const btn = document.getElementById(`tab-${t}-btn`);
    if (el && btn) {
      if (t === tabId) {
        el.classList.remove("hidden");
        btn.classList.add("border-indigo-500", "text-indigo-400");
        btn.classList.remove("border-transparent", "text-slate-400");
      } else {
        el.classList.add("hidden");
        btn.classList.remove("border-indigo-500", "text-indigo-400");
        btn.classList.add("border-transparent", "text-slate-400");
      }
    }
  });
}

function updateClock() {
  const now = new Date();
  const clock = document.getElementById("live-clock");
  if (clock) clock.innerText = now.toTimeString().split(' ')[0];
}
