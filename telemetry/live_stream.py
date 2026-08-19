"""
live_stream — Simulates GTFS-RT telemetry ingestion and publishes updates to Redis.

Publishes simulated delay updates to the 'gtfs_rt_delays' Redis channel
at regular intervals with automatic reconnection.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = "gtfs_rt_delays"
PUBLISH_INTERVAL_SEC = 2.0


def get_redis_client() -> redis.Redis:
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
    )
    return r


def main() -> None:
    print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    sys.stdout.flush()

    r = get_redis_client()

    while True:
        try:
            trip_id = random.randint(0, 50)
            stop_sequence = random.randint(1, 20)
            delay_seconds = random.randint(60, 300)

            payload = {
                "trip_id": trip_id,
                "stop_sequence": stop_sequence,
                "delay": delay_seconds,
            }

            payload_str = json.dumps(payload)
            subscribers = r.publish(REDIS_CHANNEL, payload_str)
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Published to '{REDIS_CHANNEL}' "
                f"({subscribers} subscribers): {payload_str}"
            )
            sys.stdout.flush()
            time.sleep(PUBLISH_INTERVAL_SEC)

        except (redis.ConnectionError, redis.TimeoutError) as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connection issue ({e}), retrying in 2s...", file=sys.stderr)
            sys.stderr.flush()
            time.sleep(2)
            try:
                r = get_redis_client()
                r.ping()
            except Exception:
                pass
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unexpected error: {e}", file=sys.stderr)
            sys.stderr.flush()
            time.sleep(2)


if __name__ == "__main__":
    main()
