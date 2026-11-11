"""Disruption events and how they change a plan's instance and constraints.

The current plan's routes are indexed by vehicle (route v = vehicle v). `completed[v]` is
the number of stops vehicle v has already finished (a prefix of route v). Those stops are
**frozen**: the replanned route of vehicle v starts with exactly the same stops, in the
same order. Assumption (decision 0012): frozen stops were served on the planned schedule.

Events
* vehicle_breakdown: vehicle v takes no further stops; its unfinished stops go to others.
  Its route is cut after its completed stops (the return leg is still counted, as the
  shared cost model has every route end at the depot).
* failed_delivery: a stop that was attempted but not delivered. retry=True keeps the
  customer in the plan (it is re-visited later); retry=False drops it from the instance,
  and the plan reports it as dropped. **Retry rule (decision 0023):** a retried stop is never
  a route's next unfinished stop, unless it is that route's only remaining stop (then it is
  at the end). Going straight back to a customer who was just not home is rarely useful.
* urgent_order: a new customer that must be served in the replanned plan.

Replanning a replanned plan keeps the earlier disruptions (`earlier` = the parent plan's replan record):
a vehicle that broke down stays broken, stops completed earlier stay frozen even when the client sends a
smaller count, and a retried delivery keeps the retry rule until it is completed or dropped.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.api.schemas import CustomerIn
from app.evaluation.validator import route_schedule, validate_routes
from app.models.problem import TIME_EPS, Customer, Instance


class ReplanError(ValueError):
    """The event does not fit the current plan (wrong vehicle, unknown customer, ...)."""


class _EventBase(BaseModel):
    completed: dict[int, int] = Field(default_factory=dict,
                                      description="vehicle index -> number of stops already completed")
    now: float | None = Field(None, ge=0, description="current time; time-window instances only")
    occurred_at: str | None = Field(None, description="client timestamp, stored for the record only")


class VehicleBreakdown(_EventBase):
    type: Literal["vehicle_breakdown"]
    vehicle: int = Field(ge=0)


class FailedDelivery(_EventBase):
    type: Literal["failed_delivery"]
    customer_id: int
    retry: bool = True


class UrgentOrder(_EventBase):
    type: Literal["urgent_order"]
    customer: CustomerIn


def extra_points(event) -> list[tuple[float, float]]:
    """Coordinates an event adds to the plan (an urgent order's stop), for the road matrix."""
    return [(event.customer.x, event.customer.y)] if isinstance(event, UrgentOrder) else []


Event = Annotated[VehicleBreakdown | FailedDelivery | UrgentOrder, Field(discriminator="type")]


class ReplanIn(BaseModel):
    """Body of POST /api/plans/{id}/replan. engine: "ortools" (warm start + frozen stops) or "ga" (only when no
    stop is frozen)."""
    event: Event
    engine: Literal["ortools", "ga"] = "ortools"
    time_limit_s: float = Field(5.0, gt=0)
    warm_start: bool = True
    seed: int = 0


@dataclass
class ReplanSetup:
    instance: Instance                # the real instance after the event (stored with the plan)
    timing_instance: Instance         # same, but unfinished stops not ready before `now` (solved + checked)
    frozen: list[list[int]]           # per vehicle, completed stops (customer ids)
    blocked: list[int]                # vehicles that take no further stops
    warm_routes: list[list[int]]      # current plan adjusted to the event (warm start)
    to_insert: list[int]              # customers that had no place in the adjusted plan
    dropped: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    retry: list[int] = field(default_factory=list)  # retried failed deliveries (retry rule)

    @property
    def has_frozen(self) -> bool:
        return any(self.frozen)


def _with_customers(instance: Instance, customers: list[Customer], suffix: str) -> Instance:
    d = instance.to_dict()
    d.pop("instance_id", None)
    inst = Instance.from_dict(d)
    inst.customers = customers
    inst.name = f"{instance.name}{suffix}"
    inst.source = instance.source
    inst.instance_id = inst.compute_id()
    inst._matrix = None
    return inst


def apply_event(instance: Instance, routes: list[list[int]], event: VehicleBreakdown | FailedDelivery | UrgentOrder,
                earlier: dict | None = None) -> ReplanSetup:
    k = instance.vehicle_count
    routes = [list(r) for r in routes] + [[] for _ in range(k - len(routes))]
    if len(routes) > k:
        raise ReplanError(f"plan has {len(routes)} routes but the instance has {k} vehicles")
    for v, n in event.completed.items():
        if not 0 <= v < k:
            raise ReplanError(f"completed: vehicle {v} does not exist (0..{k - 1})")
        if not 0 <= n <= len(routes[v]):
            raise ReplanError(f"completed: vehicle {v} has {len(routes[v])} stops, not {n}")
    earlier = earlier or {}
    earlier_frozen = list(earlier.get("frozen") or [])
    earlier_frozen += [[] for _ in range(k - len(earlier_frozen))]
    done = {v: max(event.completed.get(v, 0), len(earlier_frozen[v])) for v in range(k)}
    frozen = [routes[v][:done[v]] for v in range(k)]
    rest = [routes[v][done[v]:] for v in range(k)]
    frozen_ids = {c for f in frozen for c in f}
    customers = list(instance.customers)
    blocked: list[int] = sorted({int(v) for v in earlier.get("blocked") or []})
    to_insert: list[int] = []
    retry: list[int] = [c for c in earlier.get("retry") or [] if c not in frozen_ids]
    dropped: list[int] = []
    notes: list[str] = []
    suffix = ""
    kept = [v for v in range(k) if len(earlier_frozen[v]) > event.completed.get(v, 0)]
    if kept:
        notes.append("completed stops kept from the earlier replan: "
                     + ", ".join(f"vehicle {v}: {len(earlier_frozen[v])}" for v in kept))
    if blocked:
        notes.append(f"vehicle(s) {blocked} broke down in an earlier replan and take no further stops")
    if retry:
        notes.append(f"retry rule kept from the earlier replan for customer(s) {retry}")
    for v in blocked:  # a broken vehicle's route is its frozen prefix; nothing else is left on it
        to_insert += rest[v]
        rest[v] = []

    if isinstance(event, VehicleBreakdown):
        if event.vehicle >= k:
            raise ReplanError(f"vehicle {event.vehicle} does not exist (0..{k - 1})")
        if event.vehicle in blocked:
            raise ReplanError(f"vehicle {event.vehicle} already broke down in an earlier replan")
        blocked = sorted(blocked + [event.vehicle])
        moved = rest[event.vehicle]
        to_insert += moved
        rest[event.vehicle] = []
        notes.append(f"vehicle {event.vehicle} broke down after {len(frozen[event.vehicle])} completed stops; "
                     f"{len(moved)} unfinished stops reassigned")
        suffix = f"+breakdown-v{event.vehicle}"
    elif isinstance(event, FailedDelivery):
        cid = event.customer_id
        if cid not in {c.id for c in customers}:
            raise ReplanError(f"customer {cid} is not in the plan")
        if cid in frozen_ids:
            raise ReplanError(f"customer {cid} is counted as completed; a failed delivery cannot be completed")
        rest = [[c for c in r if c != cid] for r in rest]
        to_insert = [c for c in to_insert if c != cid]
        retry = [c for c in retry if c != cid]
        if event.retry:
            to_insert.append(cid)
            retry.append(cid)
            notes.append(f"delivery to customer {cid} failed; it will be re-visited, but not as a route's next stop "
                         "(only as a route's last remaining stop)")
        else:
            customers = [c for c in customers if c.id != cid]
            dropped = [cid]
            notes.append(f"delivery to customer {cid} failed; dropped from the plan as requested (not served)")
        suffix = f"+failed-{cid}"
    else:
        c = event.customer
        if c.id in {x.id for x in customers} or c.id == 0:
            raise ReplanError(f"customer id {c.id} is already used")
        customers.append(Customer(c.id, c.x, c.y, c.demand, ready_time=c.ready_time, due_time=c.due_time,
                                  service_time=c.service_time))
        to_insert.append(c.id)
        notes.append(f"urgent order {c.id} added")
        suffix = f"+urgent-{c.id}"

    new = _with_customers(instance, customers, suffix)
    timing = not_before(new, {c for f in frozen for c in f}, event.now)
    if event.now is not None and not new.has_time_windows:
        notes.append("now is ignored: the instance has no time windows")
    warm = [f + r for f, r in zip(frozen, rest)]
    leftover = insert_cheapest(timing, warm, to_insert, frozen, blocked, not_next=retry)
    if leftover:
        notes.append(f"warm start: no feasible insertion found for {leftover}; OR-Tools may start cold")
    return ReplanSetup(new, timing, frozen, blocked, warm, leftover, dropped, notes, retry)


def not_before(instance: Instance, frozen_ids: set[int], now: float | None) -> Instance:
    """Copy of the instance where no unfinished stop can start before `now` (ready = max(ready, now)).
    A vehicle can always wait, so a plan that is on time here is on time in the real instance too."""
    if now is None or not instance.has_time_windows:
        return instance
    shifted = [c if c.id in frozen_ids else Customer(c.id, c.x, c.y, c.demand, ready_time=max(c.ready_time, now),
                                                    due_time=c.due_time, service_time=c.service_time)
               for c in instance.customers]
    for c in shifted:
        if c.due_time is not None and c.ready_time > c.due_time + TIME_EPS:
            raise ReplanError(f"customer {c.id} is due at {c.due_time:g}, before the current time {now:g}; "
                              f"it cannot be served any more (drop it with a failed_delivery, retry=false)")
    return _with_customers(instance, shifted, f"@t{now:g}")


def schedule_ok(instance: Instance, route: list[int]) -> bool:
    ids = set(route)
    if sum(c.demand for c in instance.customers if c.id in ids) > instance.vehicle_capacity:
        return False
    return not instance.has_time_windows or route_schedule(instance, route).total_lateness <= TIME_EPS


def retry_too_soon(route: list[int], n_frozen: int, retry: list[int] | set[int]) -> int | None:
    """The retried customer that breaks the retry rule on this route (it is the next unfinished stop and other
    unfinished stops follow it), or None."""
    rest = route[n_frozen:]
    return rest[0] if len(rest) > 1 and rest[0] in set(retry) else None


def insert_cheapest(instance: Instance, routes: list[list[int]], customers: list[int], frozen: list[list[int]],
                    blocked: list[int], not_next: list[int] | tuple = ()) -> list[int]:
    """Insert each customer at its cheapest feasible position after the frozen prefix of a vehicle that is
    not blocked (in place). Customers in `not_next` keep the retry rule. Returns the customers that fit nowhere."""
    d = instance.distance_matrix()
    idx = instance.index_of()
    leftover = []
    for cid in customers:
        best = (math.inf, -1, -1)
        for v, r in enumerate(routes):
            if v in blocked:
                continue
            for pos in range(len(frozen[v]), len(r) + 1):
                a = idx[r[pos - 1]] if pos > 0 else 0
                b = idx[r[pos]] if pos < len(r) else 0
                added = d[a][idx[cid]] + d[idx[cid]][b] - d[a][b]
                candidate = r[:pos] + [cid] + r[pos:]
                if retry_too_soon(candidate, len(frozen[v]), not_next) is not None:
                    continue
                if added < best[0] and schedule_ok(instance, candidate):
                    best = (added, v, pos)
        if best[1] < 0:
            leftover.append(cid)
        else:
            routes[best[1]].insert(best[2], cid)
    return leftover


def check_replan(routes: list[list[int]], setup: ReplanSetup) -> list[str]:
    """Independent of the solver: frozen stops kept, blocked vehicles idle, the retry rule kept, nothing
    scheduled before `now` (the last via the validator on the timing instance)."""
    instance = setup.timing_instance
    problems = []
    extra = [r for r in routes[instance.vehicle_count:] if r]
    if extra:
        problems.append(f"{len(extra)} routes more than the {instance.vehicle_count} vehicles (vehicle index)")
    routes = routes + [[] for _ in range(instance.vehicle_count - len(routes))]
    for v, prefix in enumerate(setup.frozen):
        if routes[v][:len(prefix)] != prefix:
            problems.append(f"vehicle {v}: completed stops {prefix} changed to {routes[v][:len(prefix)]}")
    for v in setup.blocked:
        if routes[v] != setup.frozen[v]:
            problems.append(f"vehicle {v} broke down but has new stops {routes[v][len(setup.frozen[v]):]}")
    for v, prefix in enumerate(setup.frozen):
        early = retry_too_soon(routes[v], len(prefix), setup.retry)
        if early is not None:
            problems.append(f"vehicle {v}: retried customer {early} is the next stop (retry rule)")
    if setup.timing_instance is not setup.instance:
        timing = validate_routes(instance, routes)
        problems += [f"with the current time applied: {v.detail}" for v in timing.violations]
    return problems
