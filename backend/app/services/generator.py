"""Reproducible synthetic instance generator (same seed -> identical instance)."""
from __future__ import annotations

import math
import random

from app.models.problem import Customer, Instance

# Default geographic box for haversine instances (lon, lat of the depot, spread in degrees).
DEFAULT_CENTER = (77.59, 12.97)
DEFAULT_SPREAD_DEG = 0.15


def generate_instance(
    n_customers: int,
    seed: int = 0,
    metric: str = "haversine",
    demand_range: tuple[int, int] = (1, 10),
    vehicle_capacity: int | None = None,
    vehicle_count: int | None = None,
    fixed_vehicle_cost: float = 50.0,
    cost_per_distance: float = 1.0,
) -> Instance:
    rng = random.Random(seed)
    lo, hi = demand_range
    demands = [rng.randint(lo, hi) for _ in range(n_customers)]
    if metric == "haversine":
        cx, cy = DEFAULT_CENTER
        pts = [(cx + rng.uniform(-DEFAULT_SPREAD_DEG, DEFAULT_SPREAD_DEG),
                cy + rng.uniform(-DEFAULT_SPREAD_DEG, DEFAULT_SPREAD_DEG)) for _ in range(n_customers)]
        depot = (cx, cy)
    else:  # euclidean on a 100 x 100 km plane, depot at the centre
        pts = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n_customers)]
        depot = (50.0, 50.0)
    # Capacity: roughly 10 average customers per route unless given.
    cap = vehicle_capacity or max(hi, round(sum(demands) / max(n_customers, 1) * 10))
    # Fleet: minimum by total demand, +25% slack, +1 (bin-packing slack).
    vehicles = vehicle_count or math.ceil(sum(demands) / cap * 1.25) + 1
    customers = [Customer(i + 1, round(x, 6), round(y, 6), d) for i, ((x, y), d) in enumerate(zip(pts, demands))]
    return Instance(
        depot_x=round(depot[0], 6), depot_y=round(depot[1], 6), customers=customers,
        vehicle_count=vehicles, vehicle_capacity=cap, metric=metric, distance_unit="km",
        fixed_vehicle_cost=fixed_vehicle_cost, cost_per_distance=cost_per_distance,
        name=f"synthetic-n{n_customers}-seed{seed}", source="synthetic",
    )
