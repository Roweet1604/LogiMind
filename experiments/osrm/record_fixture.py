"""Record OSRM table answers into a JSON fixture, so tests replay real answers offline.

The 6 points below are SYNTHETIC (picked by hand around central Bengaluru; no customer data).
Recorded sets:
  * all 6 points with max_table=4  -> 9 batched requests (tests the batching)
  * all 6 points in one request    -> compared with the batched result in the tests
  * the first 5 points in one request (a plan before an urgent order adds point 6)

Usage (from the repo root):
  python experiments/osrm/record_fixture.py --base-url http://localhost:5000 --out <file>

The committed fixture was recorded ONCE from the public OSRM demo server (decision 0019): the demo
server is not for production and the product never uses it; LogiMind uses a self-hosted OSRM.
The script waits 1.1 s between requests (demo server policy: at most 1 request per second).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.distances.osrm import OsrmProvider, RecordingTransport  # noqa: E402

POINTS = [  # (lon, lat), synthetic
    (77.5946, 12.9716),  # depot: near the city centre
    (77.6408, 12.9784),  # Indiranagar area
    (77.6245, 12.9352),  # Koramangala area
    (77.5838, 12.9250),  # Jayanagar area
    (77.5544, 12.9982),  # Rajajinagar area
    (77.6974, 12.9591),  # Marathahalli area (the "urgent order")
]
USER_AGENT = "LogiMind-capstone-fixture-recorder/0.1 (student project; one-off test fixture)"


class SlowTransport(httpx.HTTPTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        time.sleep(1.1)
        request.headers["User-Agent"] = USER_AGENT
        return super().handle_request(request)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--profile", default="driving")
    args = ap.parse_args()
    rec = RecordingTransport(SlowTransport())
    for points, max_table in ((POINTS, 4), (POINTS, 100), (POINTS[:5], 100)):
        OsrmProvider(args.base_url, args.profile, max_table=max_table, transport=rec, timeout_s=30).matrix(points)
    out = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": args.base_url, "profile": args.profile,
        "note": "Real OSRM answers for SYNTHETIC points (no customer data). Routing data (c) OpenStreetMap "
                "contributors, ODbL. Recorded with experiments/osrm/record_fixture.py.",
        "points": [list(p) for p in POINTS],
        "responses": rec.recorded,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(rec.recorded)} responses written to {args.out}")


if __name__ == "__main__":
    main()
