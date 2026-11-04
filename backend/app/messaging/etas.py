"""ETAs computed from a stored plan.

The ETA of a stop is the planned service start from the same schedule the validator checks
(`route_schedule`): leave the depot at its opening time, travel = distance x time_per_distance,
wait when early, then the service time. It is an estimate from the plan's travel-time model
(straight-line or benchmark distances), NOT live traffic, and the messages say so.

Clock times need a shift start (when the depot opening time, time 0 + depot_ready_time, happens
in real time) and a known time unit. Without them only plan-time values are returned.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.evaluation.validator import route_schedule
from app.models.problem import Instance

UNIT_SECONDS = {"s": 1, "sec": 1, "second": 1, "seconds": 1, "min": 60, "minute": 60, "minutes": 60,
                "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600}
METHOD = ("planned service start from the route plan's travel-time model (distance x time_per_distance, "
          "waiting and service times included); not live traffic")


def unit_seconds(instance: Instance) -> int | None:
    return UNIT_SECONDS.get((instance.time_unit or "").strip().lower())


def time_model_note(instance: Instance) -> str:
    """Says plainly where travel times come from. A plan without time data uses the model's default
    (1 time unit per distance unit, i.e. 1 min per km = 60 km/h when units are km and min)."""
    if instance.has_time_windows:
        return f"from the plan: {instance.time_per_distance} {instance.time_unit} per {instance.distance_unit}"
    return (f"default assumption: {instance.time_per_distance} {instance.time_unit} per {instance.distance_unit} "
            "(the plan has no time data)")


def route_etas(instance: Instance, route: list[int], shift_start: datetime | None) -> list[dict]:
    """One entry per stop, in route order. `eta` is an ISO clock time only when shift_start is given and
    the instance's time unit is known."""
    sched = route_schedule(instance, route)
    secs = unit_seconds(instance)
    by_id = {c.id: c for c in instance.customers}
    out = []
    for seq, (cid, raw) in enumerate(zip(route, sched.starts), start=1):
        c = by_id[cid]
        start = float(raw)  # the schedule uses NumPy distances
        eta = None
        if shift_start is not None and secs is not None:
            eta = (shift_start + timedelta(seconds=start * secs)).isoformat()
        out.append({"seq": seq, "customer_id": cid, "planned_start": round(start, 3), "eta": eta,
                    "ready_time": c.ready_time, "due_time": c.due_time,
                    "late": bool(c.due_time is not None and start > c.due_time)})
    return out
