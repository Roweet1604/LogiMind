"""Synthetic instance families for the selector dataset (ALL output is synthetic).

Families (Solomon-style layouts, own generator, not copies of Solomon data):
* uniform:   customers uniform on a 100 x 100 plane
* clustered: customers around 3 to 6 Gaussian cluster centres
* mixed:     half uniform, half clustered
Time-window tightness: "none" (plain CVRP), "loose" (window = 40% of the horizon)
or "tight" (window = 10% of the horizon). Every window is placed so the customer
can be served on a direct depot round trip, so each instance passes validation.
"""
from __future__ import annotations

import math
import random

from app.models.problem import Customer, Instance

FAMILIES = ("uniform", "clustered", "mixed")
TIGHTNESS = {"none": None, "loose": 0.40, "tight": 0.10}
HORIZON = 1000.0
SERVICE_TIME = 10.0


def _points(family: str, n: int, rng: random.Random) -> list[tuple[float, float]]:
    def clamp(v: float) -> float:
        return min(100.0, max(0.0, v))

    def clustered(k: int) -> list[tuple[float, float]]:
        centres = [(rng.uniform(10, 90), rng.uniform(10, 90)) for _ in range(rng.randint(3, 6))]
        out = []
        for _ in range(k):
            cx, cy = rng.choice(centres)
            out.append((clamp(rng.gauss(cx, 6)), clamp(rng.gauss(cy, 6))))
        return out

    def uniform(k: int) -> list[tuple[float, float]]:
        return [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(k)]

    if family == "uniform":
        return uniform(n)
    if family == "clustered":
        return clustered(n)
    if family == "mixed":
        pts = uniform(n // 2) + clustered(n - n // 2)
        rng.shuffle(pts)
        return pts
    raise ValueError(f"unknown family {family!r}; expected one of {FAMILIES}")


def generate_family_instance(family: str, n_customers: int, tightness: str = "none", seed: int = 0) -> Instance:
    if tightness not in TIGHTNESS:
        raise ValueError(f"unknown tightness {tightness!r}; expected one of {tuple(TIGHTNESS)}")
    rng = random.Random(f"{family}-{n_customers}-{tightness}-{seed}")
    pts = _points(family, n_customers, rng)
    demands = [rng.randint(1, 10) for _ in range(n_customers)]
    cap = max(10, round(sum(demands) / n_customers * 10))
    width_share = TIGHTNESS[tightness]
    depot = (50.0, 50.0)
    customers = []
    for i, ((x, y), d) in enumerate(zip(pts, demands), start=1):
        x, y = round(x, 3), round(y, 3)
        if width_share is None:
            customers.append(Customer(i, x, y, d))
            continue
        t0 = math.hypot(x - depot[0], y - depot[1])
        width = width_share * HORIZON
        latest_start = HORIZON - t0 - SERVICE_TIME  # still back at the depot by the horizon
        ready = rng.uniform(0.0, max(0.0, latest_start - width))
        due = max(min(ready + width, latest_start), t0 + 0.1)  # reachable on a direct trip
        customers.append(Customer(i, x, y, d, ready_time=round(ready, 1), due_time=round(due, 1),
                                  service_time=SERVICE_TIME))
    # Fleet: demand bound + slack; tight windows need more vehicles to stay feasible.
    vehicles = math.ceil(sum(demands) / cap * 1.25) + 1
    if width_share is not None:
        vehicles = max(vehicles, math.ceil(n_customers / (4 if tightness == "tight" else 6)))
    return Instance(
        depot_x=depot[0], depot_y=depot[1], customers=customers, vehicle_count=vehicles, vehicle_capacity=cap,
        metric="euclidean", distance_unit="unit", fixed_vehicle_cost=0.0, cost_per_distance=1.0,
        name=f"synthetic-{family}-n{n_customers}-{tightness}-s{seed}", source="synthetic",
        depot_due_time=None if width_share is None else HORIZON,
    )
