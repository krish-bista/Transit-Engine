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

    /**
     * Calls the backend GetEarliestArrival RPC and returns the result
     * formatted as "HH:MM", or an error / "No route" message.
     */
    suspend fun getRoute(source: Int, target: Int, depTime: Int): String {
        return try {
            val request = routeRequest {
                sourceStop = source
                targetStop = target
                departureTime = depTime
            }
            val response = stub.getEarliestArrival(request)

            if (response.success) {
                val totalSeconds = response.arrivalTime.toInt()
                val h = totalSeconds / 3600
                val m = (totalSeconds % 3600) / 60
                "%02d:%02d".format(h, m)
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
