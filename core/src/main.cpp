#include "../include/raptor_graph.hpp"
#include "../include/routing_service.hpp"
#include "../include/telemetry_consumer.hpp"
#include <grpcpp/grpcpp.h>
#include <iostream>
#include <memory>

int main() {
  std::setvbuf(stdout, nullptr, _IONBF, 0);
  try {
    std::string stops_path = "binary_gtfs/stops.bin";
    std::string stop_times_path = "binary_gtfs/stop_times.bin";

    std::ifstream test_f(stops_path);
    if (!test_f.good()) {
      stops_path = "../../binary_gtfs/stops.bin";
      stop_times_path = "../../binary_gtfs/stop_times.bin";
    }

    auto stops = transit::load_binary_data<transit::PackedStop>(stops_path);
    auto stop_times =
        transit::load_binary_data<transit::PackedStopTime>(stop_times_path);

    std::cout << "Loaded " << stops.size() << " stops\n";
    std::cout << "Loaded " << stop_times.size() << " stop times\n";
    std::cout << "Binary data loaded successfully!\n";

    transit::RaptorGraph graph;
    graph.build_index(std::move(stops), std::move(stop_times));

    std::cout << "RAPTOR Graph initialized successfully.\n";

    transit::TelemetryConsumer consumer(graph);
    consumer.start();
    std::cout << "Telemetry Consumer started.\n";

    const std::string server_address("0.0.0.0:50051");
    transit::RoutingServiceImpl service(graph);

    grpc::ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);

    std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
    std::cout << "gRPC server listening on " << server_address << "\n";

    server->Wait();

    consumer.stop();
  } catch (const std::exception &e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }

  return 0;
}
