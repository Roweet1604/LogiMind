"""Distance sources for tenant plans (P4) and the flagged fallback.

`distance_source` on a plan request:
* "straight_line" (default, unchanged behaviour): great-circle km, travel time = distance x
  time_per_distance. No road matrix is attached.
* "osrm": road distances and travel times from the self-hosted OSRM (cached). If OSRM is not
  configured, not reachable, or cannot route a pair, the plan uses haversine x detour factor at an
  assumed speed instead, and its provenance says `fallback: true` with the reason.
* "estimate": haversine x detour factor at the assumed speed, chosen on purpose (not a fallback,
  still labelled as not road data).

The matrix is computed before the solver starts and is stored with the plan's instance, so every
engine gets the same matrix and the matrix is not charged to any engine's time budget.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.distances.base import MatrixError, MatrixTooLarge, Point, RoadMatrix, point_key
from app.distances.cache import DEFAULT_MAX_AGE_DAYS, MatrixCache, cache_key
from app.distances.haversine import DEFAULT_DETOUR_FACTOR, DEFAULT_SPEED_KMH, HaversineProvider
from app.distances.osrm import DEFAULT_MAX_NODES, DEFAULT_MAX_TABLE, OsrmProvider
from app.models.problem import Instance

log = logging.getLogger("logimind.distances")
SOURCES = ("straight_line", "osrm", "estimate")


class DistanceSourceError(ValueError):
    """The request cannot get a matrix at all (wrong coordinates, too many points)."""


def instance_points(instance: Instance) -> list[Point]:
    """Distinct (lon, lat) points of the depot and customers, in node order."""
    seen: dict[Point, None] = {}
    for x, y in [(instance.depot_x, instance.depot_y)] + [(c.x, c.y) for c in instance.customers]:
        seen.setdefault(point_key(x, y), None)
    return list(seen)


def describe(instance_dict: dict[str, Any]) -> dict[str, Any]:
    """What a stored plan's distances and travel times are based on (shown with every plan)."""
    road = instance_dict.get("road_matrix")
    if road:
        p = road.get("provenance") or {}
        keep = ("provider", "requested", "fallback", "reason", "label", "osrm_url", "profile", "data_version",
                "detour_factor", "speed_kmh", "cache", "fetched_at", "requests", "max_snap_m", "warning")
        return {k: p[k] for k in keep if k in p} | {"travel_times": "from the matrix"}
    metric = instance_dict.get("metric", "euclidean")
    if metric == "haversine":
        return {"provider": "straight_line", "requested": "straight_line", "fallback": False,
                "label": "straight line (great-circle), not road distance",
                "travel_times": "distance x time_per_distance"}
    return {"provider": metric, "requested": metric, "fallback": False,
            "label": f"{metric} distance on the given coordinates", "travel_times": "distance x time_per_distance"}


class DistanceService:
    def __init__(self, osrm: OsrmProvider | None, estimate: HaversineProvider | None = None,
                 cache: MatrixCache | None = None, max_nodes: int = DEFAULT_MAX_NODES):
        self.osrm, self.cache, self.max_nodes = osrm, cache, max_nodes
        self.estimate = estimate or HaversineProvider()

    def status(self) -> dict[str, Any]:
        return {"osrm_configured": self.osrm is not None, "osrm_url": self.osrm.base_url if self.osrm else None,
                "max_nodes": self.max_nodes, "detour_factor": self.estimate.detour_factor,
                "fallback_speed_kmh": self.estimate.speed_kmh, "cache": self.cache is not None}

    def matrix(self, points: list[Point], source: str) -> RoadMatrix:
        if source not in ("osrm", "estimate"):
            raise DistanceSourceError(f"distance_source must be one of {SOURCES}, got {source!r}")
        if len(points) > self.max_nodes:
            raise DistanceSourceError(f"{len(points)} distinct points exceed the matrix-size limit of "
                                      f"{self.max_nodes} (LOGIMIND_MATRIX_MAX_NODES)")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if source == "estimate":
            m = self.estimate.matrix(points)
            m.provenance.update(requested="estimate", fallback=False, fetched_at=now)
            return m
        reason = None
        if self.osrm is None:
            reason = "no OSRM server is configured (LOGIMIND_OSRM_URL is not set)"
        else:
            key = cache_key(f"osrm|{self.osrm.base_url}|{self.osrm.profile}", points)
            hit = self.cache.get(key) if self.cache is not None else None
            if hit is not None:
                hit.provenance.update(cache="hit")
                return hit
            try:
                m = self.osrm.matrix(points)
            except MatrixTooLarge as exc:
                raise DistanceSourceError(str(exc)) from exc
            except MatrixError as exc:
                reason = str(exc)
            else:
                m.provenance.update(requested="osrm", fallback=False, fetched_at=now)
                if self.cache is not None:
                    self.cache.put(key, m)
                m.provenance.update(cache="miss")
                return m
        log.warning("OSRM matrix not available, using the flagged fallback: %s", reason)
        m = self.estimate.matrix(points)
        m.provenance.update(requested="osrm", fallback=True, reason=reason, fetched_at=now,
                            label="FALLBACK " + m.provenance["label"] + ": OSRM was not available")
        return m

    def attach(self, instance: Instance, source: str) -> Instance:
        """Give the instance a matrix from `source` (in place) and return it. straight_line: unchanged."""
        if source == "straight_line":
            return instance
        if instance.metric != "haversine":
            raise DistanceSourceError(f"distance_source={source!r} needs lon/lat coordinates (metric haversine), "
                                      f"not {instance.metric!r}")
        instance.set_road_matrix(self.matrix(instance_points(instance), source))
        return instance

    def cover(self, instance: Instance, extra: list[Point] | tuple = ()) -> Instance:
        """Make sure an instance's matrix also covers `extra` points (e.g. an urgent order's stop), in place.
        A new matrix for all points is built from the same requested source; its provenance (fallback or not)
        is fresh."""
        road = instance.road
        if road is None:
            return instance
        points = list(dict.fromkeys(instance_points(instance) + [point_key(x, y) for x, y in extra]))
        if all(road.index_of(x, y) is not None for x, y in points):
            return instance
        instance.set_road_matrix(self.matrix(points, road.provenance.get("requested", road.provider)))
        return instance


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw in (None, "") else float(raw)


def distance_service_from_env(data_dir: Path) -> DistanceService:
    url = os.environ.get("LOGIMIND_OSRM_URL", "").strip()
    max_nodes = int(_env_float("LOGIMIND_MATRIX_MAX_NODES", DEFAULT_MAX_NODES))
    osrm = OsrmProvider(url, profile=os.environ.get("LOGIMIND_OSRM_PROFILE", "driving"),
                        max_table=int(_env_float("LOGIMIND_OSRM_MAX_TABLE", DEFAULT_MAX_TABLE)),
                        max_nodes=max_nodes, timeout_s=_env_float("LOGIMIND_OSRM_TIMEOUT_S", 10.0)) if url else None
    estimate = HaversineProvider(_env_float("LOGIMIND_DETOUR_FACTOR", DEFAULT_DETOUR_FACTOR),
                                 _env_float("LOGIMIND_FALLBACK_SPEED_KMH", DEFAULT_SPEED_KMH))
    cache = MatrixCache(Path(data_dir) / "matrix_cache.sqlite",
                        _env_float("LOGIMIND_MATRIX_CACHE_DAYS", DEFAULT_MAX_AGE_DAYS))
    return DistanceService(osrm, estimate, cache, max_nodes)
