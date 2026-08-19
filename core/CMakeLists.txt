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
find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)

# ── Locate protoc and grpc_cpp_plugin ────────
find_program(_PROTOBUF_PROTOC protoc)
find_program(_GRPC_CPP_PLUGIN_EXECUTABLE grpc_cpp_plugin)

# ── Proto file paths ────────────────────────
set(ROUTING_PROTO "${CMAKE_CURRENT_SOURCE_DIR}/proto/routing.proto")
set(PROTO_PATH    "${CMAKE_CURRENT_SOURCE_DIR}/proto")

# Generated file output paths
set(ROUTING_PB_CC  "${CMAKE_CURRENT_BINARY_DIR}/routing.pb.cc")
set(ROUTING_PB_H   "${CMAKE_CURRENT_BINARY_DIR}/routing.pb.h")
set(ROUTING_GRPC_CC "${CMAKE_CURRENT_BINARY_DIR}/routing.grpc.pb.cc")
set(ROUTING_GRPC_H  "${CMAKE_CURRENT_BINARY_DIR}/routing.grpc.pb.h")

# ── Generate protobuf sources ────────────────
add_custom_command(
    OUTPUT  "${ROUTING_PB_CC}" "${ROUTING_PB_H}"
    COMMAND "${_PROTOBUF_PROTOC}"
            --cpp_out "${CMAKE_CURRENT_BINARY_DIR}"
            -I "${PROTO_PATH}"
            "${ROUTING_PROTO}"
    DEPENDS "${ROUTING_PROTO}"
    COMMENT "Generating protobuf C++ sources from routing.proto"
)

# ── Generate gRPC sources ───────────────────
add_custom_command(
    OUTPUT  "${ROUTING_GRPC_CC}" "${ROUTING_GRPC_H}"
    COMMAND "${_PROTOBUF_PROTOC}"
            --grpc_out "${CMAKE_CURRENT_BINARY_DIR}"
            --plugin=protoc-gen-grpc="${_GRPC_CPP_PLUGIN_EXECUTABLE}"
            -I "${PROTO_PATH}"
            "${ROUTING_PROTO}"
    DEPENDS "${ROUTING_PROTO}"
    COMMENT "Generating gRPC C++ sources from routing.proto"
)

# ── Main executable ─────────────────────────
add_executable(transit_engine
    src/main.cpp
    src/raptor_router.cpp
    src/telemetry_consumer.cpp
    src/routing_service.cpp
    ${ROUTING_PB_CC}
    ${ROUTING_PB_H}
    ${ROUTING_GRPC_CC}
    ${ROUTING_GRPC_H}
)

target_include_directories(transit_engine PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_BINARY_DIR}          # generated protobuf / gRPC headers
    ${Protobuf_INCLUDE_DIRS}
)

find_package(hiredis QUIET)
if(TARGET hiredis::hiredis)
    target_link_libraries(transit_engine PRIVATE hiredis::hiredis)
else()
    target_link_libraries(transit_engine PRIVATE hiredis)
endif()

if(WIN32)
    target_link_libraries(transit_engine PRIVATE ws2_32)
endif()

if(TARGET protobuf::libprotobuf)
    target_link_libraries(transit_engine PRIVATE protobuf::libprotobuf)
else()
    target_link_libraries(transit_engine PRIVATE ${Protobuf_LIBRARIES})
endif()

if(TARGET gRPC::grpc++)
    target_link_libraries(transit_engine PRIVATE gRPC::grpc++ gRPC::grpc++_reflection)
else()
    target_link_libraries(transit_engine PRIVATE grpc++ grpc++_reflection grpc)
endif()
