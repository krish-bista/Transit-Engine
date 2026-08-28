package com.transitengine.client

import io.grpc.ManagedChannel
import io.grpc.ManagedChannelBuilder

class TransitRepository {

    private val channel: ManagedChannel =
        ManagedChannelBuilder
            .forAddress("10.0.2.2", 50051)
            .usePlaintext()
            .build()

    private val stub = RoutingEngineGrpcKt.RoutingEngineCoroutineStub(channel)

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
