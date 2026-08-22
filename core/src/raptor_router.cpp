#include "../include/raptor_router.hpp"
#include <algorithm>
#include <shared_mutex>
#include <vector>

namespace transit {

static constexpr uint32_t INF = 0xFFFFFFFF;
static constexpr uint32_t FOOTPATH_ROUTE_ID = 0xFFFFFFFE; // Marker for walking leg

RaptorRouter::RaptorRouter(const RaptorGraph& graph) : graph_(graph) {}

uint32_t RaptorRouter::find_earliest_arrival(uint32_t source_stop,
                                             uint32_t target_stop,
                                             uint32_t departure_time) {
    std::shared_lock lock(graph_.graph_mutex);

    const size_t num_stops = graph_.stops.size();
    source_stop_ = source_stop;

    parent_stop_.assign(num_stops, INF);
    parent_route_.assign(num_stops, INF);
    board_time_.assign(num_stops, 0);
    alight_time_.assign(num_stops, 0);

    if (source_stop >= num_stops || target_stop >= num_stops) {
        return INF;
    }

    if (source_stop == target_stop) {
        return departure_time;
    }

    std::vector<uint32_t> earliest_arrival(num_stops, INF);
    earliest_arrival[source_stop] = departure_time;

    std::vector<bool> marked_stops(num_stops, false);
    marked_stops[source_stop] = true;

    // Initial Footpaths from source_stop
    if (source_stop < graph_.footpath_offsets.size() - 1) {
        const uint32_t fp_begin = graph_.footpath_offsets[source_stop];
        const uint32_t fp_end   = graph_.footpath_offsets[source_stop + 1];
        for (uint32_t i = fp_begin; i < fp_end; ++i) {
            const auto& fp = graph_.footpaths[i];
            uint32_t walk_arr = departure_time + fp.duration_sec;
            if (walk_arr < earliest_arrival[fp.to_stop]) {
                earliest_arrival[fp.to_stop] = walk_arr;
                marked_stops[fp.to_stop] = true;

                parent_stop_[fp.to_stop] = source_stop;
                parent_route_[fp.to_stop] = FOOTPATH_ROUTE_ID;
                board_time_[fp.to_stop] = departure_time;
                alight_time_[fp.to_stop] = walk_arr;
            }
        }
    }

    // Loop for K=4 rounds (up to 4 transfers)
    constexpr int MAX_ROUNDS = 4;
    for (int k = 0; k < MAX_ROUNDS; ++k) {
        auto prev_arrival = earliest_arrival;
        std::vector<bool> next_marked(num_stops, false);
        std::vector<uint32_t> route_boarding(graph_.routes.size(), INF);

        // Step 1: Accumulate routes serving marked stops
        for (uint32_t stop_id = 0; stop_id < num_stops; ++stop_id) {
            if (!marked_stops[stop_id]) continue;

            const uint32_t r_begin = graph_.stop_routes_offsets[stop_id];
            const uint32_t r_end   = graph_.stop_routes_offsets[stop_id + 1];

            for (uint32_t r_idx = r_begin; r_idx < r_end; ++r_idx) {
                const uint32_t route_id = graph_.stop_routes[r_idx];
                const auto& route = graph_.routes[route_id];

                // Find position of stop_id in route
                for (uint32_t p = 0; p < route.num_stops; ++p) {
                    if (graph_.route_stops[route.route_stops_offset + p] == stop_id) {
                        if (p < route_boarding[route_id]) {
                            route_boarding[route_id] = p;
                        }
                        break;
                    }
                }
            }
        }

        // Step 2: Traverse each route with a valid boarding stop
        for (uint32_t r_id = 0; r_id < graph_.routes.size(); ++r_id) {
            if (route_boarding[r_id] == INF) continue;

            const auto& route = graph_.routes[r_id];
            uint32_t current_trip = INF;
            uint32_t board_stop_id = INF;
            uint32_t current_board_time = 0;

            for (uint32_t p = route_boarding[r_id]; p < route.num_stops; ++p) {
                const uint32_t stop_id = graph_.route_stops[route.route_stops_offset + p];

                // 1. Can we alight at stop_id on the current trip?
                if (current_trip != INF) {
                    const size_t st_idx = route.stop_times_offset +
                                          static_cast<size_t>(current_trip) * route.num_stops + p;
                    const auto& st = graph_.stop_times[st_idx];

                    if (st.arr_sec < earliest_arrival[stop_id]) {
                        earliest_arrival[stop_id] = st.arr_sec;
                        next_marked[stop_id] = true;

                        parent_stop_[stop_id] = board_stop_id;
                        parent_route_[stop_id] = r_id;
                        board_time_[stop_id] = current_board_time;
                        alight_time_[stop_id] = st.arr_sec;
                    }
                }

                // 2. Binary search earliest departing trip >= prev_arrival[stop_id]
                if (marked_stops[stop_id] && prev_arrival[stop_id] != INF) {
                    int low = 0;
                    int high = (current_trip == INF) ? static_cast<int>(route.num_trips) - 1
                                                     : static_cast<int>(current_trip) - 1;
                    int best_t = -1;

                    while (low <= high) {
                        int mid = low + (high - low) / 2;
                        const size_t st_idx = route.stop_times_offset +
                                              static_cast<size_t>(mid) * route.num_stops + p;
                        if (graph_.stop_times[st_idx].dep_sec >= prev_arrival[stop_id]) {
                            best_t = mid;
                            high = mid - 1;
                        } else {
                            low = mid + 1;
                        }
                    }

                    if (best_t != -1) {
                        current_trip = static_cast<uint32_t>(best_t);
                        board_stop_id = stop_id;
                        const size_t st_idx = route.stop_times_offset +
                                              static_cast<size_t>(best_t) * route.num_stops + p;
                        current_board_time = graph_.stop_times[st_idx].dep_sec;
                    }
                }
            }
        }

        // Step 3: Multi-modal Footpath Transfers between nearby stops (NO chained footpaths)
        std::vector<uint32_t> bus_alighted_stops;
        for (uint32_t s = 0; s < num_stops; ++s) {
            if (next_marked[s] && parent_route_[s] != FOOTPATH_ROUTE_ID) {
                bus_alighted_stops.push_back(s);
            }
        }

        for (uint32_t u : bus_alighted_stops) {
            if (u >= graph_.footpath_offsets.size() - 1) continue;
            const uint32_t fp_begin = graph_.footpath_offsets[u];
            const uint32_t fp_end   = graph_.footpath_offsets[u + 1];

            for (uint32_t i = fp_begin; i < fp_end; ++i) {
                const auto& fp = graph_.footpaths[i];
                uint32_t walk_arr = earliest_arrival[u] + fp.duration_sec;

                if (walk_arr < earliest_arrival[fp.to_stop]) {
                    earliest_arrival[fp.to_stop] = walk_arr;
                    next_marked[fp.to_stop] = true;

                    parent_stop_[fp.to_stop] = u;
                    parent_route_[fp.to_stop] = FOOTPATH_ROUTE_ID;
                    board_time_[fp.to_stop] = earliest_arrival[u];
                    alight_time_[fp.to_stop] = walk_arr;
                }
            }
        }

        // If next_marked is completely empty, break early
        bool any_marked = false;
        for (bool m : next_marked) {
            if (m) {
                any_marked = true;
                break;
            }
        }

        if (!any_marked) {
            break;
        }

        marked_stops = std::move(next_marked);
    }

    return earliest_arrival[target_stop];
}

std::vector<RaptorRouter::Leg> RaptorRouter::reconstruct_path(uint32_t target_stop) const {
    std::vector<RaptorRouter::Leg> path;
    const size_t num_stops = graph_.stops.size();
    if (target_stop >= num_stops || source_stop_ >= num_stops || source_stop_ == target_stop) {
        return path;
    }

    uint32_t curr = target_stop;
    size_t iterations = 0;
    std::vector<bool> visited(num_stops, false);

    while (curr != source_stop_ && parent_stop_[curr] != INF && parent_route_[curr] != INF && iterations < num_stops) {
        if (visited[curr]) break; // prevent cycles
        visited[curr] = true;

        RaptorRouter::Leg leg;
        leg.board_stop = parent_stop_[curr];
        leg.alight_stop = curr;
        leg.route_id = parent_route_[curr];
        leg.board_time = board_time_[curr];
        leg.alight_time = alight_time_[curr];
        path.push_back(leg);

        curr = parent_stop_[curr];
        ++iterations;
    }

    std::reverse(path.begin(), path.end());
    return path;
}

} // namespace transit
