#ifndef ROUTING_SERVICE_HPP
#define ROUTING_SERVICE_HPP

#include "raptor_graph.hpp"
#include "routing.grpc.pb.h"

#include <grpcpp/grpcpp.h>

namespace transit {

class RoutingServiceImpl final : public RoutingEngine::Service {
public:
  explicit RoutingServiceImpl(const RaptorGraph &graph);

  grpc::Status GetEarliestArrival(grpc::ServerContext *context,
                                  const RouteRequest *request,
                                  RouteResponse *response) override;

private:
  const RaptorGraph &graph_;
};

} // namespace transit

#endif // ROUTING_SERVICE_HPP
