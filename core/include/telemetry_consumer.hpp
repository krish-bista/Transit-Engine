#ifndef TELEMETRY_CONSUMER_HPP
#define TELEMETRY_CONSUMER_HPP

#include "raptor_graph.hpp"
#include <atomic>
#include <string>
#include <thread>

struct redisContext;

namespace transit {

class TelemetryConsumer {
public:
    explicit TelemetryConsumer(RaptorGraph& graph);
    ~TelemetryConsumer();

    TelemetryConsumer(const TelemetryConsumer&) = delete;
    TelemetryConsumer& operator=(const TelemetryConsumer&) = delete;

    void start(const std::string& host = "redis",
               int port = 6379,
               const std::string& channel = "gtfs_rt_delays");
    void stop();

private:
    void run(std::string host, int port, std::string channel);

    RaptorGraph&                graph_;
    std::atomic<bool>           running_{false};
    std::thread                 worker_;
    std::atomic<redisContext*>  context_{nullptr};
};

} // namespace transit

#endif // TELEMETRY_CONSUMER_HPP
