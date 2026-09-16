import struct
import tempfile
from pathlib import Path
import pandas as pd
import pytest

from telemetry.gtfs_compiler import hms_to_seconds, build_id_map

def test_hms_to_seconds_valid():
    assert hms_to_seconds("00:00:00") == 0
    assert hms_to_seconds("01:00:00") == 3600
    assert hms_to_seconds("12:30:45") == 12 * 3600 + 30 * 60 + 45
    assert hms_to_seconds("24:15:00") == 24 * 3600 + 15 * 60  # GTFS supports >24h trips

def test_hms_to_seconds_invalid():
    with pytest.raises(ValueError):
        hms_to_seconds("invalid")
    with pytest.raises(ValueError):
        hms_to_seconds("12:30")
    with pytest.raises(ValueError):
        hms_to_seconds("")

def test_build_id_map():
    s = pd.Series(["101", "102", "103", "101"])
    id_map = build_id_map(s)
    assert len(id_map) == 3
    assert set(id_map.keys()) == {"101", "102", "103"}
    assert set(id_map.values()) == {0, 1, 2}

def test_binary_stop_packing_roundtrip():
    stop_fmt = "<Idd"
    sid = 42
    lat = 48.4284
    lon = -89.2642
    
    packed = struct.pack(stop_fmt, sid, lat, lon)
    assert len(packed) == struct.calcsize(stop_fmt)
    
    unpacked_sid, unpacked_lat, unpacked_lon = struct.unpack(stop_fmt, packed)
    assert unpacked_sid == sid
    assert unpacked_lat == pytest.approx(lat)
    assert unpacked_lon == pytest.approx(lon)

def test_binary_stop_times_packing_roundtrip():
    st_fmt = "<5I"
    tid = 10
    sid = 25
    arr_sec = 36000
    dep_sec = 36060
    seq = 3
    
    packed = struct.pack(st_fmt, tid, sid, arr_sec, dep_sec, seq)
    assert len(packed) == struct.calcsize(st_fmt)
    
    u_tid, u_sid, u_arr, u_dep, u_seq = struct.unpack(st_fmt, packed)
    assert (u_tid, u_sid, u_arr, u_dep, u_seq) == (tid, sid, arr_sec, dep_sec, seq)
