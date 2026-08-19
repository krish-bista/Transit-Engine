package com.transitengine.client

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch

class RouteViewModel : ViewModel() {

    private val repository = TransitRepository()

    var sourceStop   by mutableStateOf("")
        private set
    var targetStop   by mutableStateOf("")
        private set
    var departureTime by mutableStateOf("")
        private set
    var result       by mutableStateOf("")
        private set
    var isLoading    by mutableStateOf(false)
        private set

    fun onSourceChanged(value: String)    { sourceStop = value }
    fun onTargetChanged(value: String)    { targetStop = value }
    fun onDepTimeChanged(value: String)   { departureTime = value }

    fun findRoute() {
        val src  = sourceStop.toIntOrNull() ?: return
        val tgt  = targetStop.toIntOrNull() ?: return
        val dep  = departureTime.toIntOrNull() ?: return

        isLoading = true
        result = ""

        viewModelScope.launch {
            result = repository.getRoute(src, tgt, dep)
            isLoading = false
        }
    }

    override fun onCleared() {
        super.onCleared()
        repository.shutdown()
    }
}
