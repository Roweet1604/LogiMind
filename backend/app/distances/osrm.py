"""Self-hosted OSRM table service (P4): road distances and travel times.

One `GET /table/v1/{profile}/{lon,lat;...}?annotations=distance,duration` per block.
OSRM limits the number of locations per table request (`--max-table-size`, default 100),
so larger matrices are split: points go into chunks of max_table // 2, and every ordered
pair of chunks (A, B) is one request with A as sources and B as destinations (A + B is at
most max_table locations). Above `max_nodes` the matrix is refused (MatrixTooLarge).

Only a self-hosted server is meant here (no hosted routing services, CLAUDE.md). Tests use
recorded responses through `ReplayTransport`, so they run offline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.distances.base import POINT_DECIMALS, MatrixError, MatrixTooLarge, Point, RoadMatrix

DEFAULT_MAX_TABLE = 100   # OSRM's own default --max-table-size
DEFAULT_MAX_NODES = 250   # our limit per plan (matrix stored with the plan; decision 0019)
FAR_SNAP_M = 500.0        # a point this far from the nearest road is reported in the provenance


def _fmt(v: float) -> str:
    return f"{v:.{POINT_DECIMALS}f}".rstrip("0").rstrip(".")


class OsrmProvider:
    name = "osrm"

    def __init__(self, base_url: str, profile: str = "driving", max_table: int = DEFAULT_MAX_TABLE,
                 max_nodes: int = DEFAULT_MAX_NODES, timeout_s: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        if max_table < 2:
            raise ValueError("max_table must be >= 2")
        self.base_url, self.profile = base_url.rstrip("/"), profile
        self.max_table, self.max_nodes, self.timeout_s = max_table, max_nodes, timeout_s
        self.transport = transport

    def blocks(self, n: int) -> list[tuple[list[int], list[int]]]:
        """(sources, destinations) index lists, one per request."""
        if n <= self.max_table:
            return [(list(range(n)), list(range(n)))]
        size = self.max_table // 2
        chunks = [list(range(i, min(i + size, n))) for i in range(0, n, size)]
        return [(a, b) for a in chunks for b in chunks]

    def matrix(self, points: list[Point]) -> RoadMatrix:
        n = len(points)
        if n > self.max_nodes:
            raise MatrixTooLarge(f"{n} points exceed the matrix-size limit of {self.max_nodes} "
                                 "(LOGIMIND_MATRIX_MAX_NODES)")
        if n < 1:
            raise MatrixError("no points")
        dist = np.full((n, n), np.nan)
        dur = np.full((n, n), np.nan)
        max_snap = 0.0
        data_version = None
        blocks = self.blocks(n)
        with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
            for src, dst in blocks:
                body = self._request(client, points, src, dst)
                d = np.array(body.get("distances"), dtype=float)
                t = np.array(body.get("durations"), dtype=float)
                if d.shape != (len(src), len(dst)) or t.shape != d.shape:
                    raise MatrixError(f"OSRM answer has shape {d.shape}, expected {(len(src), len(dst))}")
                dist[np.ix_(src, dst)] = d / 1000.0
                dur[np.ix_(src, dst)] = t
                for wp in (body.get("sources") or []) + (body.get("destinations") or []):
                    max_snap = max(max_snap, float(wp.get("distance") or 0.0))
                data_version = body.get("data_version", data_version)
        bad = np.argwhere(~np.isfinite(dist) | ~np.isfinite(dur))
        if len(bad):
            i, j = (int(v) for v in bad[0])
            raise MatrixError(f"OSRM found no road route from point {i} to point {j} "
                              f"({len(bad)} pair(s) without a route)")
        np.fill_diagonal(dist, 0.0)
        np.fill_diagonal(dur, 0.0)
        prov: dict[str, Any] = {
            "provider": self.name, "osrm_url": self.base_url, "profile": self.profile,
            "requests": len(blocks), "max_table": self.max_table, "max_snap_m": round(max_snap, 1),
            "label": f"road network (OSRM, profile {self.profile})"}
        if data_version:
            prov["data_version"] = data_version
        if max_snap > FAR_SNAP_M:
            prov["warning"] = (f"a point is {max_snap:.0f} m from the nearest road; its distances start "
                               "at that road point")
        return RoadMatrix(points, dist, dur, prov)

    def _request(self, client: httpx.Client, points: list[Point], src: list[int], dst: list[int]) -> dict:
        ids = src if src == dst else src + dst
        coords = ";".join(f"{_fmt(points[i][0])},{_fmt(points[i][1])}" for i in ids)
        params = {"annotations": "distance,duration"}
        if src != dst:
            params["sources"] = ";".join(str(k) for k in range(len(src)))
            params["destinations"] = ";".join(str(len(src) + k) for k in range(len(dst)))
        url = f"{self.base_url}/table/v1/{self.profile}/{coords}"
        try:
            resp = client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise MatrixError(f"OSRM not reachable at {self.base_url}: {type(exc).__name__}: {exc}") from exc
        try:
            body = resp.json()
        except ValueError:
            raise MatrixError(f"OSRM answered HTTP {resp.status_code} without JSON") from None
        if resp.status_code != 200 or body.get("code") != "Ok":
            raise MatrixError(f"OSRM error (HTTP {resp.status_code}): {body.get('code')}: {body.get('message', '')}")
        return body


# ---- recorded fixtures (tests run offline) ----------------------------------------------------
def request_key(request: httpx.Request) -> str:
    """Path plus sorted query, independent of the host, so a recording replays on any base URL."""
    query = sorted(httpx.QueryParams(request.url.query).multi_items())
    return request.url.path + ("?" + "&".join(f"{k}={v}" for k, v in query) if query else "")


class RecordingTransport(httpx.BaseTransport):
    """Wraps a real transport and keeps every answer (used by experiments/osrm/record_fixture.py)."""

    def __init__(self, inner: httpx.BaseTransport | None = None):
        self.inner = inner or httpx.HTTPTransport()
        self.recorded: dict[str, dict[str, Any]] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        resp = self.inner.handle_request(request)
        resp.read()
        self.recorded[request_key(request)] = {"status": resp.status_code, "body": json.loads(resp.content)}
        return httpx.Response(resp.status_code, content=resp.content, headers={"content-type": "application/json"})


class ReplayTransport(httpx.BaseTransport):
    """Answers only requests present in a recorded fixture; anything else fails loudly."""

    def __init__(self, fixture: dict[str, Any] | str | Path):
        if not isinstance(fixture, dict):
            fixture = json.loads(Path(fixture).read_text(encoding="utf-8"))
        self.responses: dict[str, dict[str, Any]] = fixture["responses"]
        self.calls: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        key = request_key(request)
        self.calls.append(key)
        if key not in self.responses:
            raise RuntimeError(f"request not in the recorded fixture: {key}")
        r = self.responses[key]
        return httpx.Response(r["status"], json=r["body"])
