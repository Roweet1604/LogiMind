"""Cheap instance features for the engine selector (no solver calls).

All features are computed from the instance and the time budget only, so the
selector can run before any solver starts.
"""
from __future__ import annotations

import math

import numpy as np

from app.models.problem import Instance

FEATURE_NAMES = (
    "n_customers", "budget_s", "log_budget_s", "budget_per_customer_ms",
    "has_tw", "tw_width_rel_mean", "tw_tight_share", "service_rel",
    "demand_fill", "nn_dist_rel", "nn_dist_cv", "depot_offset_rel",
)


def extract_features(instance: Instance, budget_s: float) -> dict[str, float]:
    n = len(instance.customers)
    d = instance.distance_matrix()
    cust = d[1:, 1:].astype(float).copy()
    np.fill_diagonal(cust, np.inf)
    nn = cust.min(axis=1) if n > 1 else np.zeros(1)
    depot_d = d[0, 1:].astype(float)
    mean_depot = float(depot_d.mean()) if n else 0.0
    xs = np.array([c.x for c in instance.customers], dtype=float)
    ys = np.array([c.y for c in instance.customers], dtype=float)
    centroid = (float(xs.mean()), float(ys.mean())) if n else (instance.depot_x, instance.depot_y)
    # Depot offset uses plane coordinates; fine for the planar synthetic and benchmark sets.
    offset = math.hypot(instance.depot_x - centroid[0], instance.depot_y - centroid[1])

    has_tw = bool(instance.has_time_windows)
    width_rel = tight = service_rel = 0.0
    if has_tw:
        dues = [c.due_time for c in instance.customers if c.due_time is not None]
        horizon = instance.depot_due_time or (max(dues) if dues else 0.0) or 1.0
        widths = np.array([((c.due_time if c.due_time is not None else horizon) - c.ready_time) / horizon
                           for c in instance.customers])
        width_rel = float(widths.mean())
        tight = float((widths < 0.2).mean())
        service_rel = float(np.mean([c.service_time for c in instance.customers]) / horizon)

    fill = instance.total_demand / max(instance.vehicle_capacity * instance.vehicle_count, 1)
    return {
        "n_customers": float(n),
        "budget_s": float(budget_s),
        "log_budget_s": math.log(max(budget_s, 1e-3)),
        "budget_per_customer_ms": 1000.0 * budget_s / max(n, 1),
        "has_tw": float(has_tw),
        "tw_width_rel_mean": width_rel,
        "tw_tight_share": tight,
        "service_rel": service_rel,
        "demand_fill": float(fill),
        "nn_dist_rel": float(nn.mean() / mean_depot) if mean_depot > 0 else 0.0,
        "nn_dist_cv": float(nn.std() / nn.mean()) if n > 1 and nn.mean() > 0 else 0.0,
        "depot_offset_rel": offset / mean_depot if mean_depot > 0 else 0.0,
    }


def feature_vector(features: dict[str, float]) -> list[float]:
    return [features[k] for k in FEATURE_NAMES]
