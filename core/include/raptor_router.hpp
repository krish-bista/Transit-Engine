#ifndef RAPTOR_ROUTER_HPP
#define RAPTOR_ROUTER_HPP

#include "raptor_graph.hpp"
#include <cstdint>

namespace transit {

class RaptorRouter {
public:
    explicit RaptorRouter(const RaptorGraph& graph);

    uint32_t find_earliest_arrival(uint32_t source_stop,
                                   uint32_t target_stop,
                                   uint32_t departure_time);

private:
    const RaptorGraph& graph_;
};

} // namespace transit

#endif // RAPTOR_ROUTER_HPP
