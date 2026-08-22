package com.transitengine.client

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray

/** A transit stop parsed from assets/stops.json. */
data class Stop(val id: Int, val name: String)

class RouteViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = TransitRepository()

    // ── Stop catalogue ─────────────────────────────────────────
    var stops by mutableStateOf<List<Stop>>(emptyList())
        private set
    private var stopById: Map<Int, Stop> = emptyMap()

    init {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val json = application.assets
                    .open("stops.json")
                    .bufferedReader()
                    .use { it.readText() }
                val array = JSONArray(json)
                val parsed = ArrayList<Stop>(array.length())
                for (i in 0 until array.length()) {
                    val obj = array.getJSONObject(i)
                    parsed.add(Stop(id = obj.getInt("id"), name = obj.getString("name")))
                }
                withContext(Dispatchers.Main) {
                    stops = parsed
                    stopById = parsed.associateBy { it.id }
                    // Set sensible default source and target stops for quick testing
                    if (parsed.isNotEmpty()) {
                        selectedSource = parsed[0]
                        sourceQuery = parsed[0].name
                        if (parsed.size > 4) {
                            selectedTarget = parsed[4]
                            targetQuery = parsed[4].name
                        }
                    }
                    if (departureSeconds < 0) {
                        departureSeconds = 16 * 3600 + 15 * 60 // 16:15 default
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    /** Resolve a stop ID to its human-readable name. */
    fun stopName(id: Int): String = stopById[id]?.name ?: "Stop $id"

    // ── Source autocomplete state ──────────────────────────────
    var sourceQuery by mutableStateOf("")
        private set
    var selectedSource by mutableStateOf<Stop?>(null)
        private set

    fun onSourceQueryChanged(value: String) {
        sourceQuery = value
        val match = stops.find { it.name.equals(value.trim(), ignoreCase = true) }
        selectedSource = match
    }

    fun onSourceSelected(stop: Stop) {
        selectedSource = stop
        sourceQuery = stop.name
    }

    // ── Target autocomplete state ──────────────────────────────
    var targetQuery by mutableStateOf("")
        private set
    var selectedTarget by mutableStateOf<Stop?>(null)
        private set

    fun onTargetQueryChanged(value: String) {
        targetQuery = value
        val match = stops.find { it.name.equals(value.trim(), ignoreCase = true) }
        selectedTarget = match
    }

    fun onTargetSelected(stop: Stop) {
        selectedTarget = stop
        targetQuery = stop.name
    }

    // ── Departure time state (seconds past midnight) ───────────
    var departureSeconds by mutableIntStateOf(16 * 3600 + 15 * 60)
        private set

    fun onDepartureTimeSelected(hour: Int, minute: Int) {
        departureSeconds = hour * 3600 + minute * 60
    }

    /** Format seconds past midnight as HH:MM. */
    fun formatDepartureTime(): String {
        if (departureSeconds < 0) return ""
        val h = departureSeconds / 3600
        val m = (departureSeconds % 3600) / 60
        return "%02d:%02d".format(h, m)
    }

    // ── Route result state ─────────────────────────────────────
    val legs = mutableStateListOf<Leg>()
    var errorMessage by mutableStateOf("")
        private set
    var isLoading by mutableStateOf(false)
        private set

    fun findRoute() {
        val src = selectedSource ?: return
        val tgt = selectedTarget ?: return
        if (departureSeconds < 0) return

        isLoading = true
        errorMessage = ""
        legs.clear()

        viewModelScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    repository.getRoute(src.id, tgt.id, departureSeconds)
                }
                if (response.success && response.itineraryList.isNotEmpty()) {
                    legs.addAll(response.itineraryList)
                } else if (!response.success) {
                    errorMessage = "No route found"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message ?: "Failed to connect to routing engine"}"
            } finally {
                isLoading = false
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        repository.shutdown()
    }
}
