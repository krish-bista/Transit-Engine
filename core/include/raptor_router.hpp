#ifndef RAPTOR_ROUTER_HPP
#define RAPTOR_ROUTER_HPP

#include "raptor_graph.hpp"
#include <cstdint>
#include <vector>

namespace transit {

class RaptorRouter {
public:
    struct Leg {
        uint32_t board_stop;
        uint32_t alight_stop;
        uint32_t route_id;
        uint32_t board_time;
        uint32_t alight_time;
    };

    explicit RaptorRouter(const RaptorGraph& graph);

    uint32_t find_earliest_arrival(uint32_t source_stop,
                                   uint32_t target_stop,
                                   uint32_t departure_time);

    std::vector<Leg> reconstruct_path(uint32_t target_stop) const;

private:
    const RaptorGraph& graph_;
    uint32_t source_stop_ = 0xFFFFFFFF;
    std::vector<uint32_t> parent_stop_;
    std::vector<uint32_t> parent_route_;
    std::vector<uint32_t> board_time_;
    std::vector<uint32_t> alight_time_;
};

} // namespace transit

#endif // RAPTOR_ROUTER_HPP
