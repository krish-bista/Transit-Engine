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
     * Calls the backend GetEarliestArrival RPC and returns the raw
     * [RouteResponse] protobuf so the UI layer can format it.
     */
    suspend fun getRoute(source: Int, target: Int, depTime: Int): RouteResponse {
        val request = routeRequest {
            sourceStop = source
            targetStop = target
            departureTime = depTime
        }
        return stub.getEarliestArrival(request)
    }

    fun shutdown() {
        channel.shutdown()
    }
}
