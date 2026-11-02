"""Shared CVRP / CVRPTW problem model. Both solvers, the validator and the
metrics evaluator consume this one object, so every comparison uses identical data.

Conventions
-----------
* Node 0 is the depot. Customers are nodes 1..n in the order of `customers`.
  Solvers work on node indices; results are reported with customer IDs.
* metric="euclidean": x, y are planar coordinates already in `distance_unit`.
* metric="euclidean_nint": Euclidean rounded to the nearest integer (TSPLIB
  EUC_2D; CVRPLIB sets A/B/P/X). metric="euclidean_trunc1": Euclidean truncated
  to one decimal (CVRPLIB convention for Solomon / Gehring-Homberger).
* metric="haversine": x = longitude, y = latitude (degrees); distances are
  great-circle kilometres. This is straight-line distance, NOT road distance.
* Estimated cost = fixed_vehicle_cost * vehicles_used
                   + cost_per_distance * total_distance.
  These are synthetic cost units, not calibrated currency.

Time windows (CVRPTW)
---------------------
* Travel time between nodes = distance * time_per_distance (time units are
  whatever the instance uses, e.g. minutes; Solomon uses time = distance).
* A customer's service must START within [ready_time, due_time]. Arriving
  early means waiting; due_time=None means no upper limit.
* service_time is spent at the customer after service starts.
* Every route leaves the depot no earlier than depot_ready_time and must be
  back by depot_due_time (None = no limit).
* An instance with all defaults (no windows, no service times) is a plain CVRP
  and keeps exactly the same instance_id as before time windows existed.
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
METRICS = ("euclidean", "haversine", "euclidean_nint", "euclidean_trunc1")
# Tolerance for time-window feasibility checks (floating-point noise only).
TIME_EPS = 1e-6


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
    ready_time: float = 0.0
    due_time: float | None = None
    service_time: float = 0.0


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
    depot_ready_time: float = 0.0
    depot_due_time: float | None = None
    time_per_distance: float = 1.0
    time_unit: str = "min"
    _matrix: np.ndarray | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.instance_id:
            self.instance_id = self.compute_id()

    # ---- identity -------------------------------------------------------
    def compute_id(self) -> str:
        payload: dict[str, Any] = {
            "depot": [self.depot_x, self.depot_y],
            "customers": [[c.id, c.x, c.y, c.demand] for c in self.customers],
            "vehicles": [self.vehicle_count, self.vehicle_capacity],
            "metric": self.metric,
            "costs": [self.fixed_vehicle_cost, self.cost_per_distance],
        }
        if self.has_time_windows:  # only then, so plain CVRP ids stay unchanged
            def num(v: float | None) -> float | None:  # 15 and 15.0 must hash the same
                return None if v is None else float(v)

            payload["time"] = {
                "depot": [num(self.depot_ready_time), num(self.depot_due_time)],
                "customers": [[c.id, num(c.ready_time), num(c.due_time), num(c.service_time)]
                              for c in self.customers],
                "time_per_distance": num(self.time_per_distance),
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

    @property
    def has_time_windows(self) -> bool:
        """True if any time data differs from the plain-CVRP defaults."""
        return (self.depot_ready_time != 0.0 or self.depot_due_time is not None
                or any(c.ready_time != 0.0 or c.due_time is not None or c.service_time != 0.0
                       for c in self.customers))

    @property
    def ready_times(self) -> list[float]:
        return [self.depot_ready_time] + [c.ready_time for c in self.customers]

    @property
    def due_times(self) -> list[float]:
        """Latest service start per node; math.inf where there is no limit."""
        due = [self.depot_due_time] + [c.due_time for c in self.customers]
        return [math.inf if t is None else t for t in due]

    @property
    def service_times(self) -> list[float]:
        return [0.0] + [c.service_time for c in self.customers]

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
        coords_ok = all(math.isfinite(v) for p in coords for v in p)
        if not coords_ok:
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

        time_ok = self._validate_time_fields(errors)
        if time_ok and coords_ok and self.metric in METRICS and self.has_time_windows:
            self._validate_reachability(errors)
        if errors:
            raise InstanceValidationError(errors)

    def _validate_time_fields(self, errors: list[str]) -> bool:
        before = len(errors)

        def finite(v: Any) -> bool:
            return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

        if not (finite(self.time_per_distance) and self.time_per_distance > 0):
            errors.append(f"time_per_distance must be a positive number, got {self.time_per_distance!r}")
        if not (finite(self.depot_ready_time) and self.depot_ready_time >= 0):
            errors.append("depot_ready_time must be a finite number >= 0")
        elif self.depot_due_time is not None and not (
                finite(self.depot_due_time) and self.depot_due_time >= self.depot_ready_time):
            errors.append("depot_due_time must be a finite number >= depot_ready_time")
        for c in self.customers:
            if not (finite(c.ready_time) and c.ready_time >= 0):
                errors.append(f"customer {c.id}: ready_time must be a finite number >= 0")
            elif c.due_time is not None and not (finite(c.due_time) and c.due_time >= c.ready_time):
                errors.append(f"customer {c.id}: due_time must be a finite number >= ready_time")
            if not (finite(c.service_time) and c.service_time >= 0):
                errors.append(f"customer {c.id}: service_time must be a finite number >= 0")
        return len(errors) == before

    def _validate_reachability(self, errors: list[str]) -> None:
        """Each customer must be servable on its own direct depot round trip."""
        t = self.travel_time_matrix()
        depot_due = math.inf if self.depot_due_time is None else self.depot_due_time
        for i, c in enumerate(self.customers, start=1):
            arrival = self.depot_ready_time + t[0][i]
            if c.due_time is not None and arrival > c.due_time + TIME_EPS:
                errors.append(f"customer {c.id}: cannot be reached before due_time {c.due_time} "
                              f"(earliest arrival {arrival:.2f})")
                continue
            back = max(arrival, c.ready_time) + c.service_time + t[i][0]
            if back > depot_due + TIME_EPS:
                errors.append(f"customer {c.id}: cannot be served and return before depot_due_time "
                              f"{depot_due} (earliest return {back:.2f})")

    # ---- distances and travel times ---------------------------------------
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
                m = np.hypot(diff[..., 0], diff[..., 1])
                if self.metric == "euclidean_nint":
                    m = np.floor(m + 0.5)
                elif self.metric == "euclidean_trunc1":
                    # small epsilon so values like 0.3 stored as 0.29999.. are not truncated down
                    m = np.floor(m * 10 + 1e-9) / 10
                self._matrix = m
        return self._matrix

    def travel_time_matrix(self) -> np.ndarray:
        """Travel time between nodes = distance * time_per_distance."""
        return self.distance_matrix() * self.time_per_distance

    # ---- (de)serialisation ---------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        tw = self.has_time_windows

        def cust(c: Customer) -> dict[str, Any]:
            d: dict[str, Any] = {"id": c.id, "x": c.x, "y": c.y, "demand": c.demand}
            if tw:
                d.update(ready_time=c.ready_time, due_time=c.due_time, service_time=c.service_time)
            return d

        out: dict[str, Any] = {
            "instance_id": self.instance_id,
            "name": self.name,
            "source": self.source,
            "metric": self.metric,
            "distance_unit": self.distance_unit,
            "depot": {"x": self.depot_x, "y": self.depot_y},
            "customers": [cust(c) for c in self.customers],
            "vehicle_count": self.vehicle_count,
            "vehicle_capacity": self.vehicle_capacity,
            "fixed_vehicle_cost": self.fixed_vehicle_cost,
            "cost_per_distance": self.cost_per_distance,
            "has_time_windows": tw,
        }
        if tw:
            out["depot"].update(ready_time=self.depot_ready_time, due_time=self.depot_due_time)
            out.update(time_per_distance=self.time_per_distance, time_unit=self.time_unit)
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Instance":
        def opt(v: Any) -> float | None:
            return None if v is None else float(v)

        try:
            depot = d["depot"]
            return cls(
                depot_x=float(depot["x"]),
                depot_y=float(depot["y"]),
                customers=[Customer(int(c["id"]), float(c["x"]), float(c["y"]), c["demand"],
                                    ready_time=float(c.get("ready_time", 0.0)),
                                    due_time=opt(c.get("due_time")),
                                    service_time=float(c.get("service_time", 0.0)))
                           for c in d["customers"]],
                vehicle_count=int(d["vehicle_count"]),
                vehicle_capacity=int(d["vehicle_capacity"]),
                metric=d.get("metric", "euclidean"),
                distance_unit=d.get("distance_unit", "km"),
                fixed_vehicle_cost=float(d.get("fixed_vehicle_cost", 50.0)),
                cost_per_distance=float(d.get("cost_per_distance", 1.0)),
                name=d.get("name", ""),
                source=d.get("source", "user"),
                instance_id=d.get("instance_id", ""),
                depot_ready_time=float(depot.get("ready_time", 0.0)),
                depot_due_time=opt(depot.get("due_time")),
                time_per_distance=float(d.get("time_per_distance", 1.0)),
                time_unit=d.get("time_unit", "min"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InstanceValidationError([f"malformed instance data: {exc!r}"]) from exc
