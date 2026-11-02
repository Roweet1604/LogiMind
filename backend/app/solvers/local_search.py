"""Route-level improvement for the GA (own code; no OR-Tools).

Works on a list of routes (node indices, depot implicit) with the GA's own cost
model (`_Problem`): fixed + distance cost per route, plus lateness x late_w on
time-window instances, plus `penalty` per route above the fleet size.
Capacity is always a hard limit.

* `fleet_repair`: empties the smallest routes while there are more routes than
  vehicles, by moving each customer to its cheapest position in another route
  that has room and does not become later. Fixes the "30 routes, 25 vehicles"
  failure on Solomon R101 (P1 note).
* `local_search`: first-improvement descent with relocate, swap and intra-route
  2-opt, restricted to each customer's k nearest neighbours, until no move
  improves or the deadline passes.
"""
from __future__ import annotations

import random
import time
from typing import Any

EPS = 1e-9


def route_eval(p: Any, route: list[int]) -> tuple[float, float]:
    """(cost, lateness) of one route. Lateness = late starts + late depot return,
    the same quantity the GA's split penalises."""
    if not route:
        return 0.0, 0.0
    d = p.d
    dist = d[0][route[0]] + d[route[-1]][0]
    for a, b in zip(route, route[1:]):
        dist += d[a][b]
    late = 0.0
    if p.tw:
        t, ready, due, serv = p.t, p.ready, p.due, p.service
        now, prev = p.start_time, 0
        for c in route:
            start = now + t[prev][c]
            if start < ready[c]:
                start = ready[c]
            if start > due[c]:
                late += start - due[c]
            now, prev = start + serv[c], c
        back = now + t[prev][0]
        if back > p.depot_due:
            late += back - p.depot_due
    return p.fixed + p.cpd * dist + (p.late_w * late if p.tw else 0.0), late


def load_of(p: Any, route: list[int]) -> int:
    return sum(p.demand[c] for c in route)


def routes_to_tour(routes: list[list[int]]) -> list[int]:
    """Giant tour for the GA: the routes one after another."""
    return [c for r in routes for c in r]


def objective(p: Any, routes: list[list[int]]) -> float:
    used = [r for r in routes if r]
    return sum(route_eval(p, r)[0] for r in used) + p.penalty * max(0, len(used) - p.vehicles)


def neighbours(p: Any, k: int) -> list[list[int]]:
    """k nearest customers of every customer (index 0, the depot, gets an empty list)."""
    cache = getattr(p, "_neighbours", None)
    if cache is not None and cache[0] == k:
        return cache[1]
    d, n = p.d, p.n
    out = [[]] + [sorted((v for v in range(1, n + 1) if v != u), key=d[u].__getitem__)[:k] for u in range(1, n + 1)]
    p._neighbours = (k, out)
    return out


def fleet_repair(p: Any, routes: list[list[int]], deadline: float | None = None,
                 victims_to_try: int = 3) -> list[list[int]]:
    routes = [r[:] for r in routes if r]
    while len(routes) > p.vehicles:
        if deadline is not None and time.perf_counter() >= deadline:
            break
        emptied = False
        for vi in sorted(range(len(routes)), key=lambda i: len(routes[i]))[:victims_to_try]:
            others = [r[:] for i, r in enumerate(routes) if i != vi]
            loads = [load_of(p, r) for r in others]
            evals = [route_eval(p, r) for r in others]
            placed_all = True
            # hardest first: biggest demand, then earliest due time
            for c in sorted(routes[vi], key=lambda c: (-p.demand[c], p.due[c] if p.tw else 0.0)):
                best = None
                for oi, r in enumerate(others):
                    if loads[oi] + p.demand[c] > p.cap:
                        continue
                    base_cost, base_late = evals[oi]
                    for pos in range(len(r) + 1):
                        cost, late = route_eval(p, r[:pos] + [c] + r[pos:])
                        if late > base_late + EPS:
                            continue
                        if best is None or cost - base_cost < best[0]:
                            best = (cost - base_cost, oi, pos, cost, late)
                if best is None:
                    placed_all = False
                    break
                _, oi, pos, cost, late = best
                others[oi].insert(pos, c)
                loads[oi] += p.demand[c]
                evals[oi] = (cost, late)
            if placed_all:
                routes, emptied = others, True
                break
        if not emptied:
            break
    return routes


def local_search(p: Any, routes: list[list[int]], rng: random.Random, deadline: float | None = None,
                 k: int = 10) -> tuple[list[list[int]], int]:
    """Returns (improved routes, number of applied moves)."""
    routes = [r[:] for r in routes if r]
    costs = [route_eval(p, r)[0] for r in routes]
    loads = [load_of(p, r) for r in routes]
    where = {c: ri for ri, r in enumerate(routes) for c in r}
    near = neighbours(p, k)
    moves = 0
    customers = list(where)

    def excess_drop(ra: list[int]) -> float:
        """Objective change from the fleet penalty when route `ra` becomes empty."""
        live = sum(1 for r in routes if r)
        return -p.penalty if (not ra and live > p.vehicles) else 0.0

    improved = True
    while improved:
        improved = False
        rng.shuffle(customers)
        for u in customers:
            if deadline is not None and time.perf_counter() >= deadline:
                return [r for r in routes if r], moves
            for v in near[u]:
                a, b = where[u], where[v]
                ra, rb = routes[a], routes[b]
                iu, iv = ra.index(u), rb.index(v)
                cand = None  # (delta, {route index: new route})
                if a == b:
                    # relocate u right after / right before v, and 2-opt between u and v
                    rest = ra[:iu] + ra[iu + 1:]
                    jv = rest.index(v)
                    options = [rest[:jv + 1] + [u] + rest[jv + 1:], rest[:jv] + [u] + rest[jv:]]
                    i, j = min(iu, iv), max(iu, iv)
                    options.append(ra[:i + 1] + ra[i + 1:j + 1][::-1] + ra[j + 1:])
                    for new in options:
                        if new == ra:
                            continue
                        c_new = route_eval(p, new)[0]
                        if c_new - costs[a] < -EPS and (cand is None or c_new - costs[a] < cand[0]):
                            cand = (c_new - costs[a], {a: new})
                else:
                    # relocate u next to v (route b)
                    if loads[b] + p.demand[u] <= p.cap:
                        new_a = ra[:iu] + ra[iu + 1:]
                        ca = route_eval(p, new_a)[0]
                        for new_b in (rb[:iv + 1] + [u] + rb[iv + 1:], rb[:iv] + [u] + rb[iv:]):
                            delta = ca + route_eval(p, new_b)[0] - costs[a] - costs[b] + excess_drop(new_a)
                            if delta < -EPS and (cand is None or delta < cand[0]):
                                cand = (delta, {a: new_a, b: new_b})
                    # swap u and v
                    if (loads[a] - p.demand[u] + p.demand[v] <= p.cap
                            and loads[b] - p.demand[v] + p.demand[u] <= p.cap):
                        new_a, new_b = ra[:], rb[:]
                        new_a[iu], new_b[iv] = v, u
                        delta = route_eval(p, new_a)[0] + route_eval(p, new_b)[0] - costs[a] - costs[b]
                        if delta < -EPS and (cand is None or delta < cand[0]):
                            cand = (delta, {a: new_a, b: new_b})
                if cand is not None:
                    for ri, new in cand[1].items():
                        routes[ri] = new
                        costs[ri] = route_eval(p, new)[0]
                        loads[ri] = load_of(p, new)
                        for c in new:
                            where[c] = ri
                    moves += 1
                    improved = True
                    break
    return [r for r in routes if r], moves
