// Global State
let map;
let stopsData = [];
let routesData = [];
let sourceStopId = null;
let targetStopId = null;
let userCoords = null;
let userMarker = null;
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

  await loadStops();
  await loadRoutes();
  initWebSocket();

  setupAutocomplete("source-input", "source-results", (stop) => {
    sourceStopId = stop.id;
    highlightStopOnMap(stop, true);
    if (targetStopId) calculateRoute();
  });

  setupAutocomplete("target-input", "target-results", (stop) => {
    targetStopId = stop.id;
    highlightStopOnMap(stop, false);
    calculateRoute();
  });

  // Automatically detect user location on load
  detectUserLocation();
});

// Map Setup with warm, clear street map tiles
function initMap() {
  map = L.map("map", {
    zoomControl: false,
    attributionControl: false
  }).setView([48.406, -89.260], 13);

  // CartoDB Voyager tiles (crisp street labels, parks, water, clean human aesthetic)
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    subdomains: "abcd"
  }).addTo(map);

  stopMarkersLayer = L.layerGroup().addTo(map);
  routePolylineLayer = L.layerGroup().addTo(map);
  trackingPolylineLayer = L.layerGroup().addTo(map);
}

function centerMapOnTransit() {
  if (userCoords && map) {
    map.flyTo([userCoords.lat, userCoords.lon], 15, { duration: 1.0 });
  } else if (map) {
    map.flyTo([48.406, -89.260], 13, { duration: 1.0 });
  }
}

// Automatic User Location Detection on Load
function detectUserLocation() {
  const input = document.getElementById("source-input");
  if (!navigator.geolocation) {
    fallbackOriginLocation();
    return;
  }

  if (input) input.placeholder = "📍 Locating your position...";

  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;
      userCoords = { lat, lon };

      try {
        const res = await fetch(`/api/nearest-stop?lat=${lat}&lon=${lon}`);
        if (!res.ok) throw new Error("Could not find nearest stop");
        const nearest = await res.json();

        sourceStopId = nearest.id;
        if (input) {
          input.value = `📍 Current Location (${nearest.name})`;
        }

        // Add user GPS pulse pin on map
        showUserPositionMarker(lat, lon, nearest.name);
      } catch (err) {
        fallbackOriginLocation();
      }
    },
    (err) => {
      fallbackOriginLocation();
    },
    { timeout: 5000, enableHighAccuracy: true }
  );
}

function fallbackOriginLocation() {
  sourceStopId = 217; // Edward & Gordon default
  const sStop = stopsData.find(s => s.id === sourceStopId);
  const input = document.getElementById("source-input");
  if (input) {
    input.value = sStop ? sStop.name : "Edward & Gordon";
  }
  renderStopPins();
}

function showUserPositionMarker(lat, lon, stopName) {
  if (userMarker && map) {
    map.removeLayer(userMarker);
  }

  const icon = L.divIcon({
    className: "user-loc-wrapper",
    html: `
      <div class="relative flex items-center justify-center">
        <div class="w-7 h-7 rounded-full bg-indigo-500/20 animate-ping absolute"></div>
        <div class="w-4 h-4 rounded-full bg-indigo-600 border-2 border-white shadow-md relative z-10"></div>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });

  userMarker = L.marker([lat, lon], { icon }).addTo(map);
  userMarker.bindPopup(`<div class="p-1 font-bold text-xs">📍 Your Location (Near ${stopName})</div>`);
  map.flyTo([lat, lon], 14, { duration: 1.0 });
}

// User-Triggered GPS Button Handler
async function useCurrentLocation() {
  const input = document.getElementById("source-input");
  if (input) input.value = "📍 Locating your position...";

  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    fallbackOriginLocation();
    return;
  }

  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;
      userCoords = { lat, lon };

      try {
        const res = await fetch(`/api/nearest-stop?lat=${lat}&lon=${lon}`);
        if (!res.ok) throw new Error("Failed to find nearest stop");
        const nearest = await res.json();

        sourceStopId = nearest.id;
        if (input) input.value = `📍 Current Location (${nearest.name})`;
        showUserPositionMarker(lat, lon, nearest.name);

        if (targetStopId) calculateRoute();
      } catch (err) {
        fallbackOriginLocation();
      }
    },
    (err) => {
      fallbackOriginLocation();
    },
    { timeout: 6000 }
  );
}

// Destination Dropdown Selector Handler
function onQuickSelectDestination(stopIdStr) {
  if (!stopIdStr) return;
  const sid = parseInt(stopIdStr);
  const stop = stopsData.find(s => s.id === sid);
  
  if (stop) {
    targetStopId = stop.id;
    const input = document.getElementById("target-input");
    if (input) input.value = stop.name;

    if (!sourceStopId) {
      sourceStopId = 217;
      const sInput = document.getElementById("source-input");
      if (sInput && !sInput.value) sInput.value = "Edward & Gordon";
    }

    highlightStopOnMap(stop, false);
    calculateRoute();
  }
}

function setQuickDestination(name, stopId) {
  targetStopId = stopId;
  const input = document.getElementById("target-input");
  if (input) input.value = name;
  const sel = document.getElementById("destination-quick-select");
  if (sel) sel.value = String(stopId);

  if (!sourceStopId) {
    sourceStopId = 217;
    const sInput = document.getElementById("source-input");
    if (sInput && !sInput.value) sInput.value = "Edward & Gordon";
  }

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

// Render Stop Dots
function renderStopPins() {
  if (!stopMarkersLayer) return;
  stopMarkersLayer.clearLayers();
  if (!showStopPins) return;

  stopsData.forEach(stop => {
    let pinClass = "transit-stop-dot";
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
      <div class="p-2 space-y-1.5 text-stone-900 font-sans">
        <h4 class="font-bold text-sm text-stone-900">${stop.name}</h4>
        <div class="flex space-x-2 pt-1">
          <button onclick="setAsOrigin(${stop.id})" class="px-2.5 py-1 bg-stone-900 hover:bg-stone-800 text-white rounded-lg text-xs font-semibold shadow-sm">Start Here</button>
          <button onclick="setAsDestination(${stop.id})" class="px-2.5 py-1 bg-stone-100 hover:bg-stone-200 text-stone-800 rounded-lg text-xs font-semibold">Go Here</button>
          <button onclick="openDeparturesModal(${stop.id})" class="px-2.5 py-1 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 rounded-lg text-xs font-semibold">Buses</button>
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
    btn.classList.toggle("text-stone-400", !showStopPins);
    btn.classList.toggle("text-indigo-600", showStopPins);
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
    if (targetStopId) calculateRoute();
  }
}

function setAsDestination(stopId) {
  const stop = stopsData.find(s => s.id === stopId);
  if (stop) {
    targetStopId = stop.id;
    const input = document.getElementById("target-input");
    if (input) input.value = stop.name;
    const sel = document.getElementById("destination-quick-select");
    if (sel) sel.value = String(stopId);
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
      results.innerHTML = `<div class="p-3 text-xs text-stone-500">No stops found. Try typing a street or landmark.</div>`;
      results.classList.remove("hidden");
      return;
    }

    results.innerHTML = matches.map(s => `
      <div class="p-2.5 hover:bg-stone-50 cursor-pointer border-b border-stone-100 flex items-center justify-between transition"
           onclick="selectStop('${inputId}', '${resultsId}', ${s.id})">
        <div>
          <p class="text-sm font-semibold text-stone-900">${s.name}</p>
        </div>
        <span class="text-xs text-indigo-600 font-bold">Select</span>
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
      const sel = document.getElementById("destination-quick-select");
      if (sel) sel.value = String(stop.id);
    }
    highlightStopOnMap(stop, inputId === "source-input");
    if (sourceStopId && targetStopId) calculateRoute();
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
  if (sourceStopId && targetStopId) calculateRoute();
}

let timeMode = 'now'; // Default to 'Leave Now'

function setTimeMode(mode) {
  timeMode = mode;
  const nowBtn = document.getElementById("time-mode-now-btn");
  const schedBtn = document.getElementById("time-mode-schedule-btn");
  const pickerWindow = document.getElementById("schedule-picker-window");

  if (mode === 'now') {
    if (nowBtn) {
      nowBtn.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center space-x-1.5 bg-white text-stone-900 shadow-sm";
    }
    if (schedBtn) {
      schedBtn.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold text-stone-500 hover:text-stone-900 transition flex items-center justify-center space-x-1.5";
    }
    if (pickerWindow) pickerWindow.classList.add("hidden");
    if (sourceStopId && targetStopId) calculateRoute();
  } else {
    if (schedBtn) {
      schedBtn.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center space-x-1.5 bg-white text-stone-900 shadow-sm";
    }
    if (nowBtn) {
      nowBtn.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold text-stone-500 hover:text-stone-900 transition flex items-center justify-center space-x-1.5";
    }
    if (pickerWindow) {
      pickerWindow.classList.remove("hidden");
      const dPicker = document.getElementById("departure-date-picker");
      const tPicker = document.getElementById("departure-time-picker");
      if (dPicker && !dPicker.value) {
        const today = new Date().toISOString().split('T')[0];
        dPicker.value = today;
      }
      if (tPicker && !tPicker.value) {
        const now = new Date();
        const h = String(now.getHours()).padStart(2, '0');
        const m = String(now.getMinutes()).padStart(2, '0');
        tPicker.value = `${h}:${m}`;
      }
    }
  }
}

// Calculate Route
async function calculateRoute() {
  if (!sourceStopId || !targetStopId) {
    return;
  }

  const btn = document.getElementById("search-route-btn");
  const container = document.getElementById("route-results-container");

  let depTime = "now";
  let depDate = "today";

  if (timeMode === "now") {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    depTime = `${h}:${m}`;
    depDate = "today";
  } else {
    const dPicker = document.getElementById("departure-date-picker");
    const tPicker = document.getElementById("departure-time-picker");
    if (tPicker && tPicker.value) {
      depTime = tPicker.value;
    } else {
      const now = new Date();
      depTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    }
    depDate = (dPicker && dPicker.value) ? dPicker.value : "today";
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-white"></i><span>Finding Routes...</span>`;
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
      btn.innerHTML = `<i data-lucide="sparkles" class="w-4 h-4 text-stone-300"></i><span>Find Best Routes</span>`;
      if (window.lucide) lucide.createIcons();
    }

    if (!data.success || !data.options || data.options.length === 0) {
      if (container) {
        container.innerHTML = `
          <div class="bg-stone-50 border border-stone-200 p-4 rounded-2xl text-stone-700 text-xs space-y-1">
            <p class="font-bold text-stone-900">No Bus Routes Found</p>
            <p>${data.message || "Try picking another time or nearby stops."}</p>
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
      btn.innerHTML = `<i data-lucide="sparkles" class="w-4 h-4 text-stone-300"></i><span>Find Best Routes</span>`;
      if (window.lucide) lucide.createIcons();
    }
    if (container) {
      container.innerHTML = `
        <div class="bg-rose-50 border border-rose-200 p-4 rounded-2xl text-rose-800 text-xs">
          <p class="font-bold">Routing Error</p>
          <p>${err.message}</p>
        </div>
      `;
    }
  }
}

// 1. Render Options List (Asymmetrical Typographic Balance)
function renderOptionsList() {
  if (!currentRouteData || !currentRouteData.options) return;
  const container = document.getElementById("route-results-container");
  if (!container) return;

  const options = currentRouteData.options;

  const cardsHtml = options.map((opt, idx) => {
    const busPills = opt.itinerary.filter(l => !l.is_walking).map(l => `
      <span class="px-2.5 py-1 rounded-xl text-xs font-black text-white shadow-sm flex items-center space-x-1" style="background-color: ${l.route_color}">
        <span>${l.bus_name || `Bus ${l.bus_number}`}</span>
      </span>
    `).join("<span class='text-stone-300 text-xs font-bold'>→</span>");

    const totalWalkMins = opt.itinerary.filter(l => l.is_walking).reduce((sum, l) => sum + l.duration_mins, 0);
    const isHero = (idx === 0);

    if (isHero) {
      return `
        <div class="bg-gradient-to-b from-stone-900 to-stone-800 text-white rounded-3xl p-5 space-y-4 shadow-xl cursor-pointer transition hover:scale-[1.01]"
             onclick="startJourney(${idx})">
          
          <div class="flex items-center justify-between">
            <span class="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-white/10 text-stone-200 border border-white/10">
              Recommended Route
            </span>
            <span class="text-xs font-medium text-stone-400">${opt.bus_transfers === 0 ? 'Direct Bus' : `${opt.bus_transfers} Transfer`}</span>
          </div>

          <div class="flex items-baseline justify-between pt-1">
            <div>
              <h3 class="text-2xl font-black tracking-tight text-white">${opt.departure_time} <span class="text-stone-400 font-light">→</span> ${opt.arrival_time}</h3>
              <p class="text-xs text-stone-300 mt-1 flex items-center space-x-1.5">
                <i data-lucide="footprints" class="w-3.5 h-3.5 text-stone-400"></i>
                <span>${totalWalkMins} min walk • Leave at ${opt.departure_time}</span>
              </p>
            </div>
            <div class="text-right">
              <span class="text-2xl font-black text-emerald-400">${opt.total_duration_mins}</span>
              <span class="text-xs text-stone-300 block -mt-1">mins</span>
            </div>
          </div>

          <div class="pt-3 border-t border-white/10 flex items-center justify-between">
            <div class="flex items-center space-x-1.5 flex-wrap gap-1">
              ${busPills || "<span class='text-xs text-sky-400 font-bold'>Walk</span>"}
            </div>
            <span class="text-xs font-bold text-stone-200 hover:text-white flex items-center space-x-1">
              <span>View Guide</span>
              <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
            </span>
          </div>
        </div>
      `;
    }

    return `
      <div class="bg-white border border-stone-200/90 hover:border-stone-400 rounded-2xl p-4 space-y-3 transition cursor-pointer shadow-sm"
           onclick="startJourney(${idx})">
        <div class="flex items-center justify-between">
          <div>
            <span class="text-[10px] font-bold uppercase tracking-wider text-stone-400">Option ${idx + 1}</span>
            <h4 class="text-base font-bold text-stone-900 mt-0.5">${opt.departure_time} → ${opt.arrival_time}</h4>
          </div>
          <div class="text-right">
            <span class="text-base font-extrabold text-stone-900">${opt.total_duration_mins} min</span>
            <span class="text-[11px] text-stone-500 block">${opt.bus_transfers === 0 ? 'Direct' : `${opt.bus_transfers} transfer`}</span>
          </div>
        </div>

        <div class="flex items-center justify-between pt-2 border-t border-stone-100">
          <div class="flex items-center space-x-1.5 flex-wrap gap-1">
            ${busPills}
          </div>
          <span class="text-xs text-stone-500 font-medium">Select</span>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="flex items-center justify-between px-1">
      <span class="text-xs font-extrabold uppercase tracking-wider text-stone-400">Suggested Itineraries</span>
      <span class="text-xs text-stone-500 font-medium">${options.length} departures</span>
    </div>
    <div class="space-y-3">
      ${cardsHtml}
    </div>
  `;

  if (window.lucide) lucide.createIcons();
  if (options[0]) drawRouteGeometry(options[0].itinerary);
}

// 2. Active Step-by-Step Personalized Journey Mode (The Stepper)
function startJourney(optionIndex) {
  selectedOptionIndex = optionIndex;
  isJourneyActive = true;

  const container = document.getElementById("route-results-container");
  if (!container || !currentRouteData || !currentRouteData.options) return;

  const opt = currentRouteData.options[optionIndex];

  // Set up live bus tracking in HUD without hijacking map focus
  const firstBusLeg = opt.itinerary.find(l => !l.is_walking);
  if (firstBusLeg && firstBusLeg.live_vehicle) {
    trackBus(firstBusLeg.live_vehicle.vehicle_id, firstBusLeg.bus_number, firstBusLeg.board_stop.lat, firstBusLeg.board_stop.lon, firstBusLeg.bus_name, false);
  }

  const legsHtml = opt.itinerary.map((leg, i) => {
    if (leg.is_walking) {
      return `
        <div class="flex items-start space-x-3.5 py-1">
          <div class="flex flex-col items-center shrink-0">
            <span class="w-6 h-6 rounded-full bg-sky-50 border border-sky-200 text-sky-700 flex items-center justify-center text-xs font-bold">
              <i data-lucide="footprints" class="w-3.5 h-3.5"></i>
            </span>
            <div class="w-0.5 h-8 bg-dashed border-l border-dashed border-sky-300 my-1"></div>
          </div>
          <div class="flex-1 min-w-0 pt-0.5">
            <div class="flex items-baseline justify-between">
              <h5 class="text-xs font-bold text-stone-900">${leg.action_title}</h5>
              <span class="text-xs font-semibold text-sky-700">${leg.duration_mins} min</span>
            </div>
            <p class="text-[11px] text-stone-500 mt-0.5">${leg.distance_m}m walk • Leave by ${leg.board_time_formatted}</p>
          </div>
        </div>
      `;
    }

    const liveVeh = leg.live_vehicle;
    return `
      <div class="bg-white border border-stone-200/90 rounded-2xl p-4 space-y-3.5 shadow-sm">
        
        <!-- Leg Title & Badge -->
        <div class="flex items-center justify-between border-b border-stone-100 pb-3">
          <div class="flex items-center space-x-2.5">
            <span class="px-3 py-1 rounded-xl text-xs font-black text-white shadow-sm flex items-center space-x-1"
                  style="background-color: ${leg.route_color}">
              <i data-lucide="bus" class="w-3.5 h-3.5 mr-1"></i>
              <span>BUS ${leg.bus_number}</span>
            </span>
            <div>
              <h4 class="text-sm font-extrabold text-stone-900 leading-tight">${leg.bus_name}</h4>
              <span class="text-xs text-emerald-700 font-semibold flex items-center space-x-1 mt-0.5">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>Board at ${leg.board_time_formatted}</span>
              </span>
            </div>
          </div>
          <span class="text-xs font-bold text-stone-700 bg-stone-100 px-2.5 py-1 rounded-lg">${leg.duration_mins} min ride</span>
        </div>

        <!-- Stepper Node Details -->
        <div class="relative pl-5 space-y-3 border-l-2 ml-2.5 py-0.5" style="border-color: ${leg.route_color}">
          
          <!-- Boarding Stop -->
          <div class="relative">
            <span class="absolute -left-[27px] top-1 w-3.5 h-3.5 rounded-full border-2 border-white shadow-sm" style="background-color: ${leg.route_color}"></span>
            <div>
              <span class="text-[10px] font-bold uppercase tracking-wider text-stone-400 block">Boarding Station</span>
              <p class="text-xs font-bold text-stone-900">${leg.board_stop.name}</p>
              <span class="text-[11px] text-stone-500">Departure: <strong class="text-stone-800">${leg.board_time_formatted}</strong></span>
            </div>
          </div>

          <!-- Ride Summary Banner -->
          <div class="text-xs text-stone-600 bg-stone-50 px-3 py-2 rounded-xl border border-stone-200/80 flex items-center justify-between">
            <span>🚌 Stay on bus for <strong>${leg.stops_count} stops</strong> (~${leg.duration_mins} mins)</span>
          </div>

          <!-- Alighting Stop -->
          <div class="relative">
            <span class="absolute -left-[27px] top-1 w-3.5 h-3.5 rounded-full border-2 border-white bg-stone-900 shadow-sm"></span>
            <div>
              <span class="text-[10px] font-bold uppercase tracking-wider text-stone-400 block">Get Off Station</span>
              <p class="text-xs font-bold text-stone-900">${leg.alight_stop.name}</p>
              <span class="text-[11px] text-stone-500">Arrives at: <strong class="text-stone-800">${leg.alight_time_formatted}</strong></span>
            </div>
          </div>

        </div>

        <!-- Live Vehicle Radar Action (Click to focus on bus) -->
        ${liveVeh ? `
          <button onclick="trackBus('${liveVeh.vehicle_id}', '${leg.bus_number}', ${leg.board_stop.lat}, ${leg.board_stop.lon}, '${leg.bus_name}', true)"
                  class="w-full py-2.5 px-3.5 bg-stone-50 hover:bg-stone-100 border border-stone-200 text-stone-800 font-bold text-xs rounded-xl shadow-sm flex items-center justify-between transition btn-tactile">
            <span class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
              <span>Live Bus GPS (${liveVeh.distance_m}m away)</span>
            </span>
            <span class="text-indigo-600 font-extrabold">Track Bus Live →</span>
          </button>
        ` : ''}

      </div>
    `;
  }).join("");

  container.innerHTML = `
    <!-- Top Action Header -->
    <div class="flex items-center justify-between pb-1">
      <button onclick="exitJourney()" class="px-3 py-1.5 bg-stone-100 hover:bg-stone-200 text-xs font-bold text-stone-700 rounded-xl transition flex items-center space-x-1.5 border border-stone-200 btn-tactile">
        <i data-lucide="arrow-left" class="w-3.5 h-3.5"></i>
        <span>All Routes</span>
      </button>
      <span class="text-xs text-stone-500 font-bold">Option ${optionIndex + 1} • ${opt.total_duration_mins} mins</span>
    </div>

    <!-- Active Summary Banner -->
    <div class="bg-stone-900 text-white rounded-3xl p-5 space-y-2 shadow-xl">
      <div class="flex items-center justify-between">
        <div>
          <span class="text-[10px] text-stone-400 uppercase font-bold tracking-wider">Your Trip</span>
          <h3 class="text-2xl font-black text-white tracking-tight">${opt.departure_time} → ${opt.arrival_time}</h3>
        </div>
        <div class="text-right">
          <span class="px-3 py-1 rounded-full bg-white/10 text-emerald-400 font-bold text-xs border border-white/10">
            ${opt.total_duration_mins} mins
          </span>
          <p class="text-[11px] text-stone-400 mt-1">${opt.bus_transfers === 0 ? 'Direct Ride' : `${opt.bus_transfers} transfer`}</p>
        </div>
      </div>
    </div>

    <!-- Step by Step Stepper -->
    <div class="space-y-3 pt-1">
      <h4 class="text-xs font-extrabold uppercase tracking-wider text-stone-400 px-1">Step-by-Step Directions</h4>
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
  if (!routePolylineLayer || !map) return;
  routePolylineLayer.clearLayers();
  const allCoords = [];

  itinerary.forEach((leg, idx) => {
    if (leg.geometry && leg.geometry.length > 0) {
      // Filter out invalid coords
      const validCoords = leg.geometry.filter(pt => 
        Array.isArray(pt) && pt.length >= 2 && !isNaN(pt[0]) && !isNaN(pt[1]) && pt[0] !== 0 && pt[1] !== 0
      );

      if (validCoords.length > 0) {
        if (leg.is_walking) {
          const line = L.polyline(validCoords, {
            color: "#0284c7",
            weight: 4,
            dashArray: "6, 8",
            opacity: 0.9
          });
          line.bindTooltip(`🚶 ${leg.action_title}`, { sticky: true });
          routePolylineLayer.addLayer(line);
        } else {
          const line = L.polyline(validCoords, {
            color: leg.route_color || "#4338ca",
            weight: 6,
            opacity: 0.95,
            lineCap: "round",
            lineJoin: "round"
          });
          line.bindTooltip(`🚍 ${leg.bus_name}`, { sticky: true });
          routePolylineLayer.addLayer(line);
        }
        allCoords.push(...validCoords);
      }
    }

    // Add board stop pin
    if (leg.board_stop && leg.board_stop.lat && leg.board_stop.lon) {
      const isStart = (idx === 0);
      const icon = L.divIcon({
        className: "route-stop-wrapper",
        html: `
          <div class="px-2 py-0.5 rounded-lg text-[10px] font-bold text-white shadow-md flex items-center space-x-1" 
               style="background-color: ${isStart ? '#4338ca' : (leg.route_color || '#18181b')}">
            <span>${isStart ? '📍 Start' : '🔄 Transfer'}</span>
          </div>
        `,
        iconSize: [60, 20],
        iconAnchor: [30, 10]
      });
      const m = L.marker([leg.board_stop.lat, leg.board_stop.lon], { icon });
      m.bindPopup(`<b>${isStart ? 'Starting Point' : 'Transfer Point'}</b><br>${leg.board_stop.name}`);
      routePolylineLayer.addLayer(m);
    }
  });

  // Add final destination pin
  const lastLeg = itinerary[itinerary.length - 1];
  if (lastLeg && lastLeg.alight_stop && lastLeg.alight_stop.lat && lastLeg.alight_stop.lon) {
    const icon = L.divIcon({
      className: "route-dest-wrapper",
      html: `
        <div class="px-2 py-0.5 rounded-lg text-[10px] font-bold bg-emerald-700 text-white shadow-md flex items-center space-x-1">
          <span>🏁 Destination</span>
        </div>
      `,
      iconSize: [80, 20],
      iconAnchor: [40, 10]
    });
    const destMarker = L.marker([lastLeg.alight_stop.lat, lastLeg.alight_stop.lon], { icon });
    destMarker.bindPopup(`<b>Destination</b><br>${lastLeg.alight_stop.name}`);
    routePolylineLayer.addLayer(destMarker);
  }

  if (allCoords.length > 0) {
    try {
      map.fitBounds(L.latLngBounds(allCoords), { padding: [60, 60], maxZoom: 16 });
    } catch (e) {
      console.warn("fitBounds error:", e);
    }
  }
}

// Live Bus Tracking Mode
function trackBus(vehicleId, busNumber, boardLat, boardLon, busTitle, focusCamera = false) {
  trackedVehicleId = vehicleId;
  trackedBoardStop = { lat: boardLat, lon: boardLon };

  const hud = document.getElementById("tracking-hud");
  const pill = document.getElementById("hud-bus-pill");
  const title = document.getElementById("hud-bus-title");
  const idEl = document.getElementById("hud-bus-id");

  if (pill) pill.innerText = `BUS ${busNumber}`;
  if (title) title.innerText = busTitle || `Bus ${busNumber}`;
  if (idEl) idEl.innerText = `Approaching your stop`;
  if (hud) hud.classList.remove("hidden");

  // Only focus camera if explicitly requested (e.g. clicking Live Bus GPS button)
  if (focusCamera) {
    const marker = busMarkers[vehicleId];
    if (marker && map) {
      map.flyTo(marker.getLatLng(), 16, { duration: 1.0 });
      marker.openPopup();
    }
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
      color: "#0284c7",
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

  const telemetryText = document.getElementById("telemetry-status-text");
  if (telemetryText) telemetryText.innerText = `${vehicles.length} buses moving`;

  vehicles.forEach(v => {
    const vid = v.vehicle_id;
    const isTracked = (vid === trackedVehicleId);

    if (!busMarkers[vid]) {
      const icon = L.divIcon({
        className: "transit-pill-wrapper",
        html: `
          <div class="transit-bus-pill ${isTracked ? 'tracked' : ''}" style="background-color: ${v.route_color};">
            <span>${v.route_id}</span>
          </div>
        `,
        iconSize: [36, 24],
        iconAnchor: [18, 12]
      });

      const marker = L.marker([v.lat, v.lon], { icon }).addTo(map);
      marker.bindPopup(`
        <div class="p-2 space-y-1 text-stone-900 font-sans">
          <div class="flex items-center space-x-2">
            <span class="px-2 py-0.5 rounded text-xs font-bold text-white shadow-sm" style="background: ${v.route_color}">${v.bus_name || `Bus ${v.route_id}`}</span>
            <h4 class="font-bold text-sm">${v.vehicle_id}</h4>
          </div>
          <div class="flex items-center justify-between text-xs pt-1 border-t border-stone-100 mt-1">
            <span>Speed: ${Math.round(v.speed_kmh)} km/h</span>
            <span class="font-bold text-emerald-700">On Time</span>
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
    <div class="bg-white border border-stone-200/90 p-3.5 rounded-2xl space-y-2 hover:border-stone-800 transition cursor-pointer shadow-sm btn-tactile"
         onclick="focusVehicle('${v.vehicle_id}')">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2.5">
          <span class="px-2.5 py-0.5 rounded-xl text-xs font-black text-white shadow-sm" style="background-color: ${v.route_color}">
            BUS ${v.route_id}
          </span>
          <span class="text-xs font-bold text-stone-800">${v.bus_name || `Bus ${v.route_id}`}</span>
        </div>
        <span class="text-xs font-semibold text-emerald-700">On Time</span>
      </div>

      <div class="text-xs text-stone-500 flex items-center justify-between">
        <span>Live Road GPS</span>
        <span class="font-bold text-stone-800">${Math.round(v.speed_kmh)} km/h</span>
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
  const list = document.getElementById("modal-departures-list");
  const modal = document.getElementById("departures-modal");

  if (stopNameEl) stopNameEl.innerText = stop.name;
  if (list) list.innerHTML = `<div class="p-4 text-center text-xs text-stone-400">Loading scheduled departures...</div>`;
  if (modal) modal.classList.remove("hidden");

  try {
    const res = await fetch(`/api/stops/${stopId}/departures`);
    const data = await res.json();
    if (!data.departures || data.departures.length === 0) {
      if (list) list.innerHTML = `<div class="p-4 text-center text-xs text-stone-400">No scheduled departures in next 2 hours.</div>`;
      return;
    }

    if (list) {
      list.innerHTML = data.departures.map(d => `
        <div class="bg-stone-50 border border-stone-200/80 p-3 rounded-2xl flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <span class="px-2.5 py-1 rounded-xl text-xs font-black text-white shadow-sm" style="background-color: ${d.route_color || '#4338CA'}">
              ${d.route_id ? `BUS ${d.route_id}` : 'BUS'}
            </span>
            <div>
              <p class="text-xs font-bold text-stone-900">${d.bus_name || d.headsign}</p>
              <span class="text-xs text-stone-500">Departs at ${d.departure_time}</span>
            </div>
          </div>
          <span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">
            On Time
          </span>
        </div>
      `).join("");
    }
  } catch (err) {
    if (list) list.innerHTML = `<div class="p-4 text-center text-xs text-rose-600">Error loading departures.</div>`;
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
        btn.classList.add("bg-white", "text-stone-900", "shadow-sm", "border", "border-stone-200/80");
        btn.classList.remove("text-stone-500", "hover:text-stone-900", "hover:bg-white/70");
      } else {
        el.classList.add("hidden");
        btn.classList.remove("bg-white", "text-stone-900", "shadow-sm", "border", "border-stone-200/80");
        btn.classList.add("text-stone-500", "hover:text-stone-900", "hover:bg-white/70");
      }
    }
  });
}
