package com.transitengine.client

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import org.json.JSONArray

/** A transit stop parsed from assets/stops.json. */
data class Stop(val id: Int, val name: String)

class RouteViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = TransitRepository()

    // ── Stop catalogue ─────────────────────────────────────────
    val stops: List<Stop>

    init {
        val json = application.assets
            .open("stops.json")
            .bufferedReader()
            .use { it.readText() }
        val array = JSONArray(json)
        val parsed = mutableListOf<Stop>()
        for (i in 0 until array.length()) {
            val obj = array.getJSONObject(i)
            parsed.add(Stop(id = obj.getInt("id"), name = obj.getString("name")))
        }
        stops = parsed
    }

    private val stopById: Map<Int, Stop> = stops.associateBy { it.id }

    /** Resolve a stop ID to its human-readable name. */
    fun stopName(id: Int): String = stopById[id]?.name ?: "Stop $id"

    // ── Source autocomplete state ──────────────────────────────
    var sourceQuery by mutableStateOf("")
        private set
    var selectedSource by mutableStateOf<Stop?>(null)
        private set

    fun onSourceQueryChanged(value: String) {
        sourceQuery = value
        if (selectedSource != null && value != selectedSource!!.name) {
            selectedSource = null
        }
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
        if (selectedTarget != null && value != selectedTarget!!.name) {
            selectedTarget = null
        }
    }

    fun onTargetSelected(stop: Stop) {
        selectedTarget = stop
        targetQuery = stop.name
    }

    // ── Departure time state (seconds past midnight) ───────────
    var departureSeconds by mutableIntStateOf(-1)
        private set

    /** Called when the user confirms the Material 3 TimePicker. */
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
                val response = repository.getRoute(src.id, tgt.id, departureSeconds)
                if (response.success && response.itineraryList.isNotEmpty()) {
                    legs.addAll(response.itineraryList)
                } else if (!response.success) {
                    errorMessage = "No route found"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
