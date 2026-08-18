#include "../include/raptor_graph.hpp"
#include "../include/raptor_router.hpp"
#include "../include/telemetry_consumer.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <thread>

int main() {
  try {
    auto stops = transit::load_binary_data<transit::PackedStop>(
        "../../binary_gtfs/stops.bin");
    auto stop_times = transit::load_binary_data<transit::PackedStopTime>(
        "../../binary_gtfs/stop_times.bin");

    std::cout << "Loaded " << stops.size() << " stops\n";
    std::cout << "Loaded " << stop_times.size() << " stop times\n";
    std::cout << "Binary data loaded successfully!\n";

    transit::RaptorGraph graph;
    graph.build_index(std::move(stops), std::move(stop_times));

    std::cout << "RAPTOR Graph initialized successfully.\n";

    transit::RaptorRouter router(graph);
    uint32_t departure_time = 28800; // 08:00:00 AM (28800 seconds)

    // Initial query before live updates
    uint32_t arrival_time = router.find_earliest_arrival(0, 10, departure_time);
    if (arrival_time == 0xFFFFFFFF) {
      std::cout << "Initial Query (Stop 0 -> Stop 10 @ 08:00 AM): No route found\n";
    } else {
      uint32_t h = arrival_time / 3600;
      uint32_t m = (arrival_time % 3600) / 60;
      uint32_t s = arrival_time % 60;
      std::cout << "Initial Query (Stop 0 -> Stop 10 @ 08:00 AM): Earliest arrival = "
                << arrival_time << " s ("
                << (h < 10 ? "0" : "") << h << ":"
                << (m < 10 ? "0" : "") << m << ":"
                << (s < 10 ? "0" : "") << s << ")\n";
    }

    // Start Telemetry Consumer and wait 5 seconds for live delays
    std::cout << "\nStarting Telemetry Consumer (waiting 5 seconds for live updates)...\n";
    transit::TelemetryConsumer consumer(graph);
    consumer.start();

    std::this_thread::sleep_for(std::chrono::seconds(5));

    // Re-run query after live delays
    std::cout << "\nRe-running Query with Live Telemetry...\n";
    uint32_t updated_arrival = router.find_earliest_arrival(0, 10, departure_time);
    if (updated_arrival == 0xFFFFFFFF) {
      std::cout << "Post-Telemetry Query (Stop 0 -> Stop 10 @ 08:00 AM): No route found\n";
    } else {
      uint32_t h = updated_arrival / 3600;
      uint32_t m = (updated_arrival % 3600) / 60;
      uint32_t s = updated_arrival % 60;
      std::cout << "Post-Telemetry Query (Stop 0 -> Stop 10 @ 08:00 AM): Earliest arrival = "
                << updated_arrival << " s ("
                << (h < 10 ? "0" : "") << h << ":"
                << (m < 10 ? "0" : "") << m << ":"
                << (s < 10 ? "0" : "") << s << ")\n";
    }

    consumer.stop();
  } catch (const std::exception &e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }

  return 0;
}
