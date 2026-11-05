"""Road matrix types shared by every distance provider (P4).

A `RoadMatrix` holds distances (km) and travel times (seconds) between a list of
lon/lat points, plus a provenance record that says where the numbers came from
(OSRM, or the flagged straight-line x detour-factor fallback). An Instance that
carries one uses it for both distances and travel times, so every engine, the
validator, the metrics and the ETAs see the same numbers.

Values are rounded on construction (1 m, 0.1 s) so the in-memory matrix the
solvers use is exactly the one stored with the plan.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

Point = tuple[float, float]  # (lon, lat) in degrees
POINT_DECIMALS = 6           # ~0.1 m; also the precision sent to OSRM


def point_key(lon: float, lat: float) -> Point:
    return (round(float(lon), POINT_DECIMALS), round(float(lat), POINT_DECIMALS))


class MatrixError(RuntimeError):
    """A provider could not produce a matrix (server down, bad answer, unroutable pair)."""


class MatrixTooLarge(MatrixError):
    """More points than the configured matrix-size limit."""


@dataclass
class RoadMatrix:
    points: list[Point]
    distances_km: np.ndarray
    durations_s: np.ndarray
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.points = [point_key(*p) for p in self.points]
        n = len(self.points)
        self.distances_km = np.round(np.asarray(self.distances_km, dtype=float), 3)
        self.durations_s = np.round(np.asarray(self.durations_s, dtype=float), 1)
        if self.distances_km.shape != (n, n) or self.durations_s.shape != (n, n):
            raise MatrixError(f"matrix shape {self.distances_km.shape}/{self.durations_s.shape} "
                              f"does not match {n} points")
        if not (np.isfinite(self.distances_km).all() and np.isfinite(self.durations_s).all()):
            raise MatrixError("matrix has missing or non-finite values")
        if (self.distances_km < 0).any() or (self.durations_s < 0).any():
            raise MatrixError("matrix has negative values")
        self._index = {p: i for i, p in enumerate(self.points)}

    @property
    def provider(self) -> str:
        return self.provenance.get("provider", "")

    @property
    def fallback(self) -> bool:
        return bool(self.provenance.get("fallback"))

    def index_of(self, lon: float, lat: float) -> int | None:
        return self._index.get(point_key(lon, lat))

    def digest(self) -> str:
        """Identity of the numbers and their source (not of when or how they were fetched)."""
        payload = {"provider": self.provider, "fallback": self.fallback, "points": self.points,
                   "d": self.distances_km.tolist(), "t": self.durations_s.tolist()}
        return hashlib.sha1(json.dumps(payload).encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {"points": [list(p) for p in self.points], "distances_km": self.distances_km.tolist(),
                "durations_s": self.durations_s.tolist(), "provenance": self.provenance}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RoadMatrix":
        return cls([tuple(p) for p in d["points"]], np.array(d["distances_km"], dtype=float),
                   np.array(d["durations_s"], dtype=float), dict(d.get("provenance") or {}))


class DistanceProvider(Protocol):
    name: str

    def matrix(self, points: list[Point]) -> RoadMatrix:
        """Full matrix between distinct points (row = from, column = to). Raises MatrixError."""
        ...
