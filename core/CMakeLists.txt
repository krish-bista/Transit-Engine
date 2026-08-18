cmake_minimum_required(VERSION 3.20)
project(transit-engine-core
    VERSION   0.1.0
    LANGUAGES CXX
)

# ── C++20 ────────────────────────────────────
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ── Dependencies ─────────────────────────────
find_package(Protobuf REQUIRED)
find_package(gRPC    CONFIG REQUIRED)

# ── Protobuf code generation ────────────────
file(GLOB PROTO_FILES "${CMAKE_CURRENT_SOURCE_DIR}/proto/*.proto")

if(PROTO_FILES)
    protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS ${PROTO_FILES})
endif()

# ── Main executable ─────────────────────────
add_executable(transit_engine
    src/main.cpp
    ${PROTO_SRCS}
    ${PROTO_HDRS}
)

target_include_directories(transit_engine PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_BINARY_DIR}          # generated protobuf headers
)

target_link_libraries(transit_engine PRIVATE
    protobuf::libprotobuf
    gRPC::grpc++
    gRPC::grpc++_reflection
)
