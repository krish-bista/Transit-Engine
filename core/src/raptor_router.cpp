#include "../include/raptor_router.hpp"
#include <algorithm>
#include <shared_mutex>
#include <vector>

namespace transit {

static constexpr uint32_t INF = 0xFFFFFFFF;

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

    // Loop for K=4 rounds (Max transfers)
    constexpr int MAX_ROUNDS = 4;
    for (int k = 0; k < MAX_ROUNDS; ++k) {
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

                // If on a trip, evaluate arrival time at current stop
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

                // If this stop was marked (or we're not on a trip yet), check if we can board a trip / earlier trip
                if (marked_stops[stop_id] && earliest_arrival[stop_id] != INF) {
                    for (uint32_t t = 0; t < route.num_trips; ++t) {
                        const size_t st_idx = route.stop_times_offset +
                                              static_cast<size_t>(t) * route.num_stops + p;
                        const auto& st = graph_.stop_times[st_idx];

                        if (st.dep_sec >= earliest_arrival[stop_id]) {
                            if (current_trip == INF || t < current_trip) {
                                current_trip = t;
                                board_stop_id = stop_id;
                                current_board_time = st.dep_sec;
                            }
                            break; // First matching trip is the earliest departing
                        }
                    }
                } else if (current_trip == INF && earliest_arrival[stop_id] != INF) {
                    for (uint32_t t = 0; t < route.num_trips; ++t) {
                        const size_t st_idx = route.stop_times_offset +
                                              static_cast<size_t>(t) * route.num_stops + p;
                        const auto& st = graph_.stop_times[st_idx];

                        if (st.dep_sec >= earliest_arrival[stop_id]) {
                            current_trip = t;
                            board_stop_id = stop_id;
                            current_board_time = st.dep_sec;
                            break;
                        }
                    }
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
    while (curr != source_stop_ && parent_stop_[curr] != INF && parent_route_[curr] != INF && iterations < num_stops) {
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
