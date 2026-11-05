"""Straight-line estimate: great-circle distance x detour factor, at an assumed average speed.

This is NOT road data. It is used when it is requested explicitly ("estimate") or as the
flagged fallback when OSRM is unavailable; the provenance says which, with the factor and
the speed, so the plan never presents it as a road distance.
"""
from __future__ import annotations

import numpy as np

from app.distances.base import Point, RoadMatrix
from app.models.problem import EARTH_RADIUS_KM

# Assumptions (decision 0019), configurable with LOGIMIND_DETOUR_FACTOR / LOGIMIND_FALLBACK_SPEED_KMH.
DEFAULT_DETOUR_FACTOR = 1.3
DEFAULT_SPEED_KMH = 25.0


def great_circle_km(points: list[Point]) -> np.ndarray:
    pts = np.radians(np.array(points, dtype=float).reshape(-1, 2))
    lon, lat = pts[:, 0], pts[:, 1]
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


class HaversineProvider:
    name = "haversine_detour"

    def __init__(self, detour_factor: float = DEFAULT_DETOUR_FACTOR, speed_kmh: float = DEFAULT_SPEED_KMH):
        if not detour_factor >= 1.0:
            raise ValueError("detour_factor must be >= 1")
        if not speed_kmh > 0:
            raise ValueError("speed_kmh must be > 0")
        self.detour_factor, self.speed_kmh = float(detour_factor), float(speed_kmh)

    def matrix(self, points: list[Point]) -> RoadMatrix:
        d = great_circle_km(points) * self.detour_factor
        t = d / self.speed_kmh * 3600.0
        return RoadMatrix(points, d, t, {
            "provider": self.name, "detour_factor": self.detour_factor, "speed_kmh": self.speed_kmh,
            "label": f"estimate: straight line x {self.detour_factor:g} at {self.speed_kmh:g} km/h "
                     "(not road data)"})
