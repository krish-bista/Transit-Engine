FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    cmake \
    g++ \
    make \
    pkg-config \
    libprotobuf-dev \
    protobuf-compiler \
    libgrpc++-dev \
    protobuf-compiler-grpc \
    libhiredis-dev \
    nlohmann-json3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY core/ /app/core/
COPY binary_gtfs/ /app/binary_gtfs/

RUN cmake -B build -S core && cmake --build build --target transit_engine

EXPOSE 50051

ENTRYPOINT ["./build/transit_engine"]
