#ifndef RAPTOR_GRAPH_HPP
#define RAPTOR_GRAPH_HPP

#include "transit_data.hpp"
#include <cstdint>
#include <utility>
#include <vector>

namespace transit {

// ── Route descriptor for the flattened RAPTOR index ─────────────────────────

struct Route {
    uint32_t id;
    uint32_t num_stops;
    uint32_t num_trips;
    uint32_t route_stops_offset;
    uint32_t stop_times_offset;
};

// ── Data-Oriented graph index for RAPTOR ────────────────────────────────────

class RaptorGraph {
public:
    // Raw GTFS data
    std::vector<PackedStop>     stops;
    std::vector<PackedStopTime> stop_times;

    // Flattened 2D array mappings
    std::vector<uint32_t> stop_routes_offsets;  // CSR-style offsets: per-stop → routes
    std::vector<uint32_t> stop_routes;          // flat list of route indices per stop
    std::vector<uint32_t> route_stops;          // flat list of stop ids per route

    // Route descriptors
    std::vector<Route> routes;

    /// Moves raw data into the graph and initializes index structures.
    /// Complex route-grouping logic will be added in a subsequent step.
    void build_index(std::vector<PackedStop>&& raw_stops,
                     std::vector<PackedStopTime>&& raw_stop_times) {
        stops      = std::move(raw_stops);
        stop_times = std::move(raw_stop_times);

        // Initialize CSR offset array: one entry per stop + sentinel
        stop_routes_offsets.resize(stops.size() + 1, 0);
    }
};

} // namespace transit

#endif // RAPTOR_GRAPH_HPP
