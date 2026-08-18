#include "../include/raptor_graph.hpp"
#include <iostream>

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
  } catch (const std::exception &e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }

  return 0;
}
