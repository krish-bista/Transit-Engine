package com.transitengine.client

import io.grpc.ManagedChannel
import io.grpc.ManagedChannelBuilder

/**
 * Network client for the Transit Routing gRPC service.
 *
 * Uses 10.0.2.2 — the Android emulator's alias for the host machine's
 * localhost — so the emulator can reach our C++ gRPC server on port 50051.
 */
class TransitRepository {

    private val channel: ManagedChannel =
        ManagedChannelBuilder
            .forAddress("10.0.2.2", 50051)
            .usePlaintext()
            .build()

    private val stub = RoutingEngineGrpcKt.RoutingEngineCoroutineStub(channel)

    private fun formatTime(seconds: Int): String {
        val h = seconds / 3600
        val m = (seconds % 3600) / 60
        return "%02d:%02d".format(h, m)
    }

    /**
     * Calls the backend GetEarliestArrival RPC and returns the result
     * formatted with arrival time and itinerary legs.
     */
    suspend fun getRoute(source: Int, target: Int, depTime: Int): String {
        return try {
            val request = routeRequest {
                sourceStop = source
                targetStop = target
                departureTime = depTime
            }
            val response = stub.getEarliestArrival(request)

            if (response.success && response.itineraryList.isNotEmpty()) {
                val lastLeg = response.itineraryList.last()
                val arrivalStr = formatTime(lastLeg.alightTime.toInt())
                val sb = StringBuilder()
                sb.append("Arrival: $arrivalStr\n\nItinerary:")
                for ((idx, leg) in response.itineraryList.withIndex()) {
                    val bTime = formatTime(leg.boardTime.toInt())
                    val aTime = formatTime(leg.alightTime.toInt())
                    sb.append("\n${idx + 1}. Route ${leg.routeId}: Stop ${leg.boardStop} ($bTime) -> Stop ${leg.alightStop} ($aTime)")
                }
                sb.toString()
            } else if (response.success) {
                formatTime(depTime)
            } else {
                "No route found"
            }
        } catch (e: Exception) {
            "Error: ${e.message}"
        }
    }

    fun shutdown() {
        channel.shutdown()
    }
}
