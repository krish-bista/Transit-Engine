#ifndef RAPTOR_GRAPH_HPP
#define RAPTOR_GRAPH_HPP

#include "transit_data.hpp"
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <shared_mutex>
#include <unordered_map>
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
  mutable std::shared_mutex graph_mutex;

  // Raw GTFS data
  std::vector<PackedStop> stops;
  std::vector<PackedStopTime> stop_times;

  // Flattened 2D array mappings
  std::vector<uint32_t>
      stop_routes_offsets;           // CSR-style offsets: per-stop → routes
  std::vector<uint32_t> stop_routes; // flat list of route indices per stop
  std::vector<uint32_t> route_stops; // flat list of stop ids per route

  // Route descriptors
  std::vector<Route> routes;

  /// Builds the Data-Oriented RAPTOR graph index from raw stops and stop_times.
  void build_index(std::vector<PackedStop> &&raw_stops,
                   std::vector<PackedStopTime> &&raw_stop_times) {
    stops = std::move(raw_stops);

    // Clear member containers
    stop_times.clear();
    routes.clear();
    route_stops.clear();
    stop_routes.clear();
    stop_routes_offsets.clear();

    // 1. Group by Trip: sort by trip_id, then stop_sequence
    std::sort(raw_stop_times.begin(), raw_stop_times.end(),
              [](const PackedStopTime &a, const PackedStopTime &b) {
                if (a.trip_id != b.trip_id) {
                  return a.trip_id < b.trip_id;
                }
                return a.stop_sequence < b.stop_sequence;
              });

    std::unordered_map<uint32_t, std::vector<PackedStopTime>> trip_stoptimes;
    for (const auto &st : raw_stop_times) {
      trip_stoptimes[st.trip_id].push_back(st);
    }

    // 2. Hash Stop Sequences: map unique stop_id sequences to list of trip_ids
    std::map<std::vector<uint32_t>, std::vector<uint32_t>> sequence_to_trips;
    for (const auto &[trip_id, st_vec] : trip_stoptimes) {
      std::vector<uint32_t> seq;
      seq.reserve(st_vec.size());
      for (const auto &st : st_vec) {
        seq.push_back(st.stop_id);
      }
      sequence_to_trips[seq].push_back(trip_id);
    }

    // 3. Populate Routes & Arrays
    for (auto &[seq, trip_ids] : sequence_to_trips) {
      // Sort trips within route by departure time at first stop
      std::sort(trip_ids.begin(), trip_ids.end(),
                [&](uint32_t t1, uint32_t t2) {
                  return trip_stoptimes[t1].front().dep_sec <
                         trip_stoptimes[t2].front().dep_sec;
                });

      Route route;
      route.id = static_cast<uint32_t>(routes.size());
      route.num_stops = static_cast<uint32_t>(seq.size());
      route.num_trips = static_cast<uint32_t>(trip_ids.size());
      route.route_stops_offset = static_cast<uint32_t>(route_stops.size());
      route.stop_times_offset = static_cast<uint32_t>(stop_times.size());

      for (uint32_t stop_id : seq) {
        route_stops.push_back(stop_id);
      }

      for (uint32_t trip_id : trip_ids) {
        const auto &st_vec = trip_stoptimes[trip_id];
        for (const auto &st : st_vec) {
          stop_times.push_back(st);
        }
      }

      routes.push_back(route);
    }

    // 4. Build CSR Stop-to-Route Mapping
    std::vector<std::vector<uint32_t>> stop_to_routes(stops.size());
    for (const auto &route : routes) {
      for (uint32_t i = 0; i < route.num_stops; ++i) {
        uint32_t stop_id = route_stops[route.route_stops_offset + i];
        if (stop_id < stop_to_routes.size()) {
          auto &r_list = stop_to_routes[stop_id];
          if (r_list.empty() || r_list.back() != route.id) {
            r_list.push_back(route.id);
          }
        }
      }
    }

    stop_routes_offsets.resize(stops.size() + 1, 0);
    uint32_t current_offset = 0;
    for (size_t s = 0; s < stops.size(); ++s) {
      stop_routes_offsets[s] = current_offset;
      for (uint32_t route_id : stop_to_routes[s]) {
        stop_routes.push_back(route_id);
      }
      current_offset += static_cast<uint32_t>(stop_to_routes[s].size());
    }
    stop_routes_offsets[stops.size()] = current_offset;

    // 5. Print Stats
    std::cout << "Generated " << routes.size() << " unique RAPTOR routes.\n";
  }
};

} // namespace transit

#endif // RAPTOR_GRAPH_HPP
