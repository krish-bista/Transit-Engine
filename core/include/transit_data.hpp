#ifndef TRANSIT_DATA_HPP
#define TRANSIT_DATA_HPP

#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace transit {

// ── Packed structs for zero-padding binary compatibility with Python ─────────

#pragma pack(push, 1)

struct PackedStop {
    uint32_t id;
    double   lat;
    double   lon;
};

struct PackedStopTime {
    uint32_t trip_id;
    uint32_t stop_id;
    uint32_t arr_sec;
    uint32_t dep_sec;
    uint32_t stop_sequence;
};

#pragma pack(pop)

// ── Binary loader ────────────────────────────────────────────────────────────

/// Loads a binary file written by Python's struct.pack into a vector of T.
/// Opens in binary+ate mode to determine file size upfront, validates that
/// the size is an exact multiple of sizeof(T), then block-reads the entire
/// file in a single operation.
template <typename T>
std::vector<T> load_binary_data(const std::string& filepath) {
    std::ifstream file(filepath, std::ios::binary | std::ios::ate);
    if (!file) {
        throw std::runtime_error("Failed to open binary file: " + filepath);
    }

    const auto file_size = file.tellg();
    if (file_size < 0) {
        throw std::runtime_error("Failed to determine size of: " + filepath);
    }

    if (file_size == 0) {
        return {};
    }

    if (static_cast<std::size_t>(file_size) % sizeof(T) != 0) {
        throw std::runtime_error(
            "File size (" + std::to_string(file_size) +
            " bytes) is not a multiple of record size (" +
            std::to_string(sizeof(T)) + " bytes): " + filepath);
    }

    const std::size_t count = static_cast<std::size_t>(file_size) / sizeof(T);
    std::vector<T> records(count);

    file.seekg(0, std::ios::beg);
    file.read(reinterpret_cast<char*>(records.data()),
              static_cast<std::streamsize>(file_size));

    if (!file) {
        throw std::runtime_error("Failed to read binary data from: " + filepath);
    }

    return records;
}

} // namespace transit

#endif // TRANSIT_DATA_HPP
