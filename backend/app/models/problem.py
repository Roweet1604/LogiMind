"""Shared CVRP problem model. Both solvers, the validator and the metrics
evaluator consume this one object, so every comparison uses identical data.

Conventions
-----------
* Node 0 is the depot. Customers are nodes 1..n in the order of `customers`.
  Solvers work on node indices; results are reported with customer IDs.
* metric="euclidean": x, y are planar coordinates already in `distance_unit`.
* metric="haversine": x = longitude, y = latitude (degrees); distances are
  great-circle kilometres. This is straight-line distance, NOT road distance.
* Estimated cost = fixed_vehicle_cost * vehicles_used
                   + cost_per_distance * total_distance.
  These are synthetic cost units, not calibrated currency.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

EARTH_RADIUS_KM = 6371.0088
DEPOT_NODE = 0
METRICS = ("euclidean", "haversine")


class InstanceValidationError(ValueError):
    """Raised when an instance is malformed or provably infeasible."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class Customer:
    id: int
    x: float
    y: float
    demand: int


@dataclass
class Instance:
    depot_x: float
    depot_y: float
    customers: list[Customer]
    vehicle_count: int
    vehicle_capacity: int
    metric: str = "euclidean"
    distance_unit: str = "km"
    fixed_vehicle_cost: float = 50.0
    cost_per_distance: float = 1.0
    name: str = ""
    source: str = "user"  # e.g. "synthetic", "user", "benchmark:<name>"
    instance_id: str = ""
    _matrix: np.ndarray | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.instance_id:
            self.instance_id = self.compute_id()

    # ---- identity -------------------------------------------------------
    def compute_id(self) -> str:
        payload = {
            "depot": [self.depot_x, self.depot_y],
            "customers": [[c.id, c.x, c.y, c.demand] for c in self.customers],
            "vehicles": [self.vehicle_count, self.vehicle_capacity],
            "metric": self.metric,
            "costs": [self.fixed_vehicle_cost, self.cost_per_distance],
        }
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return f"inst-{digest[:10]}"

    # ---- structure ------------------------------------------------------
    @property
    def node_ids(self) -> list[int]:
        """Customer ID for each node index (depot node 0 has ID 0)."""
        return [0] + [c.id for c in self.customers]

    @property
    def demands(self) -> list[int]:
        return [0] + [c.demand for c in self.customers]

    @property
    def total_demand(self) -> int:
        return sum(c.demand for c in self.customers)

    def index_of(self) -> dict[int, int]:
        return {cid: i for i, cid in enumerate(self.node_ids)}

    # ---- validation -----------------------------------------------------
    def validate(self) -> None:
        errors: list[str] = []
        if self.metric not in METRICS:
            errors.append(f"metric must be one of {METRICS}, got {self.metric!r}")
        if not self.customers:
            errors.append("instance has no customers")
        if self.vehicle_count < 1:
            errors.append(f"vehicle_count must be >= 1, got {self.vehicle_count}")
        if self.vehicle_capacity < 1:
            errors.append(f"vehicle_capacity must be >= 1, got {self.vehicle_capacity}")
        if self.fixed_vehicle_cost < 0 or self.cost_per_distance < 0:
            errors.append("cost parameters must be non-negative")
        coords = [(self.depot_x, self.depot_y)] + [(c.x, c.y) for c in self.customers]
        if not all(math.isfinite(v) for p in coords for v in p):
            errors.append("coordinates must be finite numbers")
        elif self.metric == "haversine" and not all(
            -180 <= x <= 180 and -90 <= y <= 90 for x, y in coords
        ):
            errors.append("haversine metric needs longitude in [-180,180] and latitude in [-90,90]")

        seen: set[int] = set()
        for c in self.customers:
            if c.id == DEPOT_NODE:
                errors.append("customer id 0 is reserved for the depot")
            if c.id in seen:
                errors.append(f"duplicate customer id {c.id}")
            seen.add(c.id)
            if not isinstance(c.demand, int) or isinstance(c.demand, bool) or c.demand <= 0:
                errors.append(f"customer {c.id}: demand must be a positive integer, got {c.demand!r}")
            elif self.vehicle_capacity >= 1 and c.demand > self.vehicle_capacity:
                errors.append(
                    f"customer {c.id}: demand {c.demand} exceeds vehicle capacity {self.vehicle_capacity}"
                )
        if self.vehicle_count >= 1 and self.vehicle_capacity >= 1:
            fleet_cap = self.vehicle_count * self.vehicle_capacity
            valid_demand = sum(c.demand for c in self.customers if isinstance(c.demand, int) and c.demand > 0)
            if valid_demand > fleet_cap:
                errors.append(f"total demand {valid_demand} exceeds total fleet capacity {fleet_cap}")
        if errors:
            raise InstanceValidationError(errors)

    # ---- distances ------------------------------------------------------
    def distance_matrix(self) -> np.ndarray:
        """(n+1)x(n+1) float matrix in `distance_unit`; computed once, shared by all solvers."""
        if self._matrix is None:
            pts = np.array([[self.depot_x, self.depot_y]] + [[c.x, c.y] for c in self.customers], dtype=float)
            if self.metric == "haversine":
                lon, lat = np.radians(pts[:, 0]), np.radians(pts[:, 1])
                dlat = lat[:, None] - lat[None, :]
                dlon = lon[:, None] - lon[None, :]
                a = np.sin(dlat / 2) ** 2 + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon / 2) ** 2
                self._matrix = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
            else:
                diff = pts[:, None, :] - pts[None, :, :]
                self._matrix = np.hypot(diff[..., 0], diff[..., 1])
        return self._matrix

    # ---- (de)serialisation ---------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "name": self.name,
            "source": self.source,
            "metric": self.metric,
            "distance_unit": self.distance_unit,
            "depot": {"x": self.depot_x, "y": self.depot_y},
            "customers": [{"id": c.id, "x": c.x, "y": c.y, "demand": c.demand} for c in self.customers],
            "vehicle_count": self.vehicle_count,
            "vehicle_capacity": self.vehicle_capacity,
            "fixed_vehicle_cost": self.fixed_vehicle_cost,
            "cost_per_distance": self.cost_per_distance,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Instance":
        try:
            return cls(
                depot_x=float(d["depot"]["x"]),
                depot_y=float(d["depot"]["y"]),
                customers=[Customer(int(c["id"]), float(c["x"]), float(c["y"]), c["demand"]) for c in d["customers"]],
                vehicle_count=int(d["vehicle_count"]),
                vehicle_capacity=int(d["vehicle_capacity"]),
                metric=d.get("metric", "euclidean"),
                distance_unit=d.get("distance_unit", "km"),
                fixed_vehicle_cost=float(d.get("fixed_vehicle_cost", 50.0)),
                cost_per_distance=float(d.get("cost_per_distance", 1.0)),
                name=d.get("name", ""),
                source=d.get("source", "user"),
                instance_id=d.get("instance_id", ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InstanceValidationError([f"malformed instance data: {exc!r}"]) from exc
