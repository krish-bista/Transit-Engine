#include "../include/routing_service.hpp"
#include "../include/raptor_router.hpp"
#include <iostream>

namespace transit {

RoutingServiceImpl::RoutingServiceImpl(const RaptorGraph &graph)
    : graph_(graph) {}

grpc::Status
RoutingServiceImpl::GetEarliestArrival(grpc::ServerContext * /*context*/,
                                       const RouteRequest *request,
                                       RouteResponse *response) {
  // Instantiate a local router per request.
  // RaptorRouter::find_earliest_arrival already acquires a std::shared_lock
  // on the graph internally, so concurrent RPCs are safe.
  RaptorRouter router(graph_);

  uint32_t arrival =
      router.find_earliest_arrival(request->source_stop(),
                                   request->target_stop(),
                                   request->departure_time());

  if (arrival == 0xFFFFFFFF) {
    response->set_success(false);
  } else {
    auto legs = router.reconstruct_path(request->target_stop());
    for (const auto &leg : legs) {
      auto *proto_leg = response->add_itinerary();
      proto_leg->set_board_stop(leg.board_stop);
      proto_leg->set_alight_stop(leg.alight_stop);
      proto_leg->set_route_id(leg.route_id);
      proto_leg->set_board_time(leg.board_time);
      proto_leg->set_alight_time(leg.alight_time);
    }
    response->set_success(true);
  }

  return grpc::Status::OK;
}

} // namespace transit
