#include "../include/telemetry_consumer.hpp"
#include <chrono>
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <hiredis/hiredis.h>
#include <nlohmann/json.hpp>

#ifdef _WIN32
#include <winsock2.h>
#else
#include <unistd.h>
#endif

namespace transit {

using json = nlohmann::json;

TelemetryConsumer::TelemetryConsumer(RaptorGraph& graph)
    : graph_(graph) {}

TelemetryConsumer::~TelemetryConsumer() {
    stop();
}

void TelemetryConsumer::start(const std::string& host, int port, const std::string& channel) {
    if (running_.exchange(true)) {
        return;
    }
    worker_ = std::thread(&TelemetryConsumer::run, this, host, port, channel);
}

void TelemetryConsumer::stop() {
    if (running_.exchange(false)) {
        redisContext* c = context_.load();
        if (c && c->fd > 0) {
#ifdef _WIN32
            shutdown(c->fd, SD_BOTH);
            closesocket(c->fd);
#else
            shutdown(c->fd, SHUT_RDWR);
            close(c->fd);
#endif
        }
        if (worker_.joinable()) {
            worker_.join();
        }
    }
}

void TelemetryConsumer::run(std::string host, int port, std::string channel) {
#ifdef _WIN32
    WSADATA wsa_data;
    WSAStartup(MAKEWORD(2, 2), &wsa_data);
#endif

    std::cout << "TelemetryConsumer: Connecting to Redis at " << host << ":" << port << "...\n";

    while (running_) {
        redisContext* c = redisConnect(host.c_str(), port);

        if (!c || c->err) {
            if (c) {
                std::cerr << "TelemetryConsumer: Connection failed: " << c->errstr << "\n";
                redisFree(c);
            } else {
                std::cerr << "TelemetryConsumer: Cannot allocate redis context\n";
            }
            for (int i = 0; i < 20 && running_; ++i) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
            continue;
        }

        context_.store(c);
        std::cout << "TelemetryConsumer: Connected to Redis. Subscribing to '" << channel << "'...\n";

        redisReply* sub_reply = static_cast<redisReply*>(
            redisCommand(c, "SUBSCRIBE %s", channel.c_str()));
        if (sub_reply) {
            freeReplyObject(sub_reply);
        }

        while (running_) {
            void* reply = nullptr;
            int status = redisGetReply(c, &reply);

            if (status == REDIS_OK && reply != nullptr) {
                redisReply* r = static_cast<redisReply*>(reply);

                if (r->type == REDIS_REPLY_ARRAY && r->elements == 3) {
                    if (r->element[0]->type == REDIS_REPLY_STRING &&
                        std::string(r->element[0]->str) == "message") {
                        const std::string payload = r->element[2]->str;

                        try {
                            auto j = json::parse(payload);
                            uint32_t trip_id       = j.value("trip_id", 0u);
                            uint32_t stop_sequence = j.value("stop_sequence", 0u);
                            uint32_t delay         = j.value("delay", 0u);

                            // Grab exclusive write lock to safely mutate graph stop_times
                            {
                                std::unique_lock lock(graph_.graph_mutex);
                                for (auto& st : graph_.stop_times) {
                                    if (st.trip_id == trip_id && st.stop_sequence == stop_sequence) {
                                        st.arr_sec += delay;
                                        st.dep_sec += delay;
                                    }
                                }
                            }

                            std::cout << "Live Update: Trip " << trip_id
                                      << " delayed by " << delay << "s\n";
                        } catch (const std::exception& e) {
                            std::cerr << "TelemetryConsumer: JSON parse error: " << e.what() << "\n";
                        }
                    }
                }
                freeReplyObject(reply);
            } else {
                if (running_) {
                    std::cerr << "TelemetryConsumer: Disconnected from Redis, reconnecting...\n";
                }
                break;
            }
        }

        context_.store(nullptr);
        redisFree(c);
    }

#ifdef _WIN32
    WSACleanup();
#endif
    std::cout << "TelemetryConsumer: Stopped.\n";
}

} // namespace transit
