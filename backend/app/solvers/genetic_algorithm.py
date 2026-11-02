"""Custom Genetic Algorithm for CVRP (own population-based search; no OR-Tools).

Representation
--------------
A chromosome is a *giant tour*: a permutation of all customers. It is decoded
into vehicle routes by an optimal "split" (Prins-style dynamic programme): the
tour is cut into consecutive segments, each segment being one route, such that
every segment respects vehicle capacity and total estimated cost
(fixed vehicle cost + cost_per_distance * distance) is minimal for that order.

Constraint handling
-------------------
* Customer coverage / no duplicates: guaranteed by the permutation encoding.
* Capacity: guaranteed by the split (segments never exceed capacity; instance
  validation ensures every single demand fits one vehicle).
* Fleet size: the split ignores the vehicle limit, so tours that decode into
  more routes than vehicles are penalised by `excess_routes * penalty`, where
  penalty is an upper bound on any feasible solution's cost. The independent
  validator still checks the final answer and reports a violation if the GA
  ends with an over-sized fleet.

Operators
---------
Selection: tournament. Crossover: order crossover (OX). Mutation: swap,
inversion or relocate (one chosen at random). Elitism: best `elite_count`
copied unchanged. Optional: a fraction of the initial population is built with
randomised nearest-neighbour tours (`nn_seed_fraction`; set 0 for a purely
random start). Termination: max generations, wall-clock limit, or stagnation. The clock is checked
between generations, so the initial population is always built and evaluated first;
with very small budgets on very large instances the GA can therefore overshoot.

Fitness is the shared cost model, so it is comparable with the OR-Tools objective
(but reported metrics are always recomputed by the shared evaluator).
"""
from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass

from app.models import result as R
from app.models.problem import Instance, InstanceValidationError
from app.solvers.local_search import fleet_repair, local_search, routes_to_tour


@dataclass
class GAConfig:
    population_size: int = 100
    max_generations: int = 500
    time_limit_s: float | None = None
    stagnation_generations: int | None = 100
    elite_count: int = 2
    tournament_size: int = 3
    crossover_rate: float = 0.9
    mutation_rate: float = 0.2
    nn_seed_fraction: float = 0.1
    # Time windows only: share of the start population ordered by due time, the
    # cost of one time unit of lateness (None = automatic, see _Problem), and
    # whether the best tour gets one repair move per generation while it is late.
    due_seed_fraction: float = 0.1
    lateness_weight: float | None = None
    tw_repair: bool = True
    # P3: empty the smallest routes when there are more routes than vehicles;
    # optional local search (relocate, swap, 2-opt) on a share of the children.
    fleet_repair: bool = True
    local_search: bool = False
    ls_rate: float = 0.2
    ls_neighbours: int = 10
    seed: int = 0

    def validate(self) -> None:
        errs = []
        if self.population_size < 4:
            errs.append("population_size must be >= 4")
        if self.max_generations < 1:
            errs.append("max_generations must be >= 1")
        if not 0 <= self.elite_count < self.population_size:
            errs.append("elite_count must be in [0, population_size)")
        if self.tournament_size < 1:
            errs.append("tournament_size must be >= 1")
        if not (0 <= self.crossover_rate <= 1 and 0 <= self.mutation_rate <= 1):
            errs.append("crossover_rate and mutation_rate must be in [0, 1]")
        if not 0 <= self.nn_seed_fraction <= 1:
            errs.append("nn_seed_fraction must be in [0, 1]")
        if not 0 <= self.due_seed_fraction <= 1 or self.nn_seed_fraction + self.due_seed_fraction > 1:
            errs.append("due_seed_fraction must be in [0, 1] and nn_seed_fraction + due_seed_fraction <= 1")
        if self.lateness_weight is not None and self.lateness_weight < 0:
            errs.append("lateness_weight must be >= 0")
        if not 0 <= self.ls_rate <= 1:
            errs.append("ls_rate must be in [0, 1]")
        if self.ls_neighbours < 1:
            errs.append("ls_neighbours must be >= 1")
        if errs:
            raise ValueError("; ".join(errs))


class _Problem:
    """Plain-list view of the instance for fast inner loops."""

    def __init__(self, inst: Instance, lateness_weight: float | None = None):
        self.d = inst.distance_matrix().tolist()
        self.demand = inst.demands
        self.cap = inst.vehicle_capacity
        self.fixed = inst.fixed_vehicle_cost
        self.cpd = inst.cost_per_distance
        self.vehicles = inst.vehicle_count
        self.n = len(self.d) - 1
        # Upper bound for any feasible solution: one depot round trip per customer.
        self.penalty = sum(2 * self.d[0][i] for i in range(1, self.n + 1)) * self.cpd + self.fixed * self.n + 1.0
        self.tw = inst.has_time_windows
        if self.tw:
            self.t = inst.travel_time_matrix().tolist()
            self.ready, self.due, self.service = inst.ready_times, inst.due_times, inst.service_times
            self.start_time, self.depot_due = inst.depot_ready_time, self.due[0]
            # Default: one time unit late costs as much as the worst feasible plan,
            # so any on-time plan beats any late one.
            self.late_w = self.penalty if lateness_weight is None else lateness_weight

    def split(self, perm: list[int]) -> tuple[float, list[list[int]]]:
        """Optimal capacity-respecting segmentation of `perm`; returns (cost, routes of node indices).

        With time windows, each route's cost also includes late_w * (lateness at
        its stops + late return to the depot). Capacity stays a hard limit."""
        n, d, dem, cap = len(perm), self.d, self.demand, self.cap
        tw = self.tw
        if tw:
            t, ready, due, serv = self.t, self.ready, self.due, self.service
            t0, depot_due, late_w = self.start_time, self.depot_due, self.late_w
        inf = float("inf")
        best = [inf] * (n + 1)
        pred = [0] * (n + 1)
        best[0] = 0.0
        for i in range(n):
            base = best[i]
            if base == inf:
                continue
            load, dist = 0, 0.0
            now, late = 0.0, 0.0
            for j in range(i, n):
                c = perm[j]
                load += dem[c]
                if load > cap:
                    break
                dist = d[0][c] if j == i else dist + d[perm[j - 1]][c]
                cost = base + self.fixed + self.cpd * (dist + d[c][0])
                if tw:
                    arrival = t0 + t[0][c] if j == i else now + t[perm[j - 1]][c]
                    start = ready[c] if arrival < ready[c] else arrival
                    if start > due[c]:
                        late += start - due[c]
                    now = start + serv[c]
                    back = now + t[c][0]
                    cost += late_w * (late + (back - depot_due if back > depot_due else 0.0))
                if cost < best[j + 1]:
                    best[j + 1] = cost
                    pred[j + 1] = i
        routes, j = [], n
        while j > 0:
            i = pred[j]
            routes.append(perm[i:j])
            j = i
        routes.reverse()
        return best[n], routes

    def fitness(self, perm: list[int]) -> float:
        cost, routes = self.split(perm)
        return cost + self.penalty * max(0, len(routes) - self.vehicles)

    def route_lateness(self, route: list[int]) -> list[float]:
        """Lateness at each stop of one route (time windows only)."""
        now, prev, out = self.start_time, 0, []
        for c in route:
            start = max(now + self.t[prev][c], self.ready[c])
            out.append(max(0.0, start - self.due[c]))
            now, prev = start + self.service[c], c
        return out


def _needs_repair(p: _Problem, perm: list[int]) -> bool:
    """Late somewhere, or more routes than vehicles (the split's other way to dodge lateness)."""
    _, routes = p.split(perm)
    return len(routes) > p.vehicles or any(late > 1e-9 for r in routes for late in p.route_lateness(r))


def repair_time_windows(p: _Problem, perm: list[int], rng: random.Random,
                        max_positions: int = 200) -> tuple[list[int], float, int]:
    """One repair move for a time-window tour: take the latest customer (or, if no
    stop is late but the split needs more routes than vehicles, a random customer
    of the shortest route) and reinsert it at the giant-tour position with the
    best fitness, trying at most `max_positions` positions.

    Returns (perm, fitness, fitness evaluations used); the input perm comes back
    unchanged if no move helps."""
    base_fit = p.fitness(perm)
    _, routes = p.split(perm)
    worst, worst_late = None, 0.0
    for r in routes:
        for c, late in zip(r, p.route_lateness(r)):
            if late > worst_late:
                worst, worst_late = c, late
    if worst is None and len(routes) > p.vehicles:
        worst = rng.choice(min(routes, key=len))
    if worst is None:
        return perm, base_fit, 1
    rest = [c for c in perm if c != worst]
    positions = list(range(len(rest) + 1))
    if len(positions) > max_positions:
        positions = rng.sample(positions, max_positions)
    best_perm, best_fit = perm, base_fit
    for pos in positions:
        cand = rest[:pos] + [worst] + rest[pos:]
        f = p.fitness(cand)
        if f < best_fit - 1e-9:
            best_perm, best_fit = cand, f
    return best_perm, best_fit, 1 + len(positions)


def order_crossover(p1: list[int], p2: list[int], rng: random.Random) -> list[int]:
    n = len(p1)
    if n < 3:
        return p1[:]
    a, b = sorted(rng.sample(range(n), 2))
    child: list[int | None] = [None] * n
    child[a:b + 1] = p1[a:b + 1]
    used = set(p1[a:b + 1])
    fill = [g for g in p2[b + 1:] + p2[:b + 1] if g not in used]
    positions = list(range(b + 1, n)) + list(range(0, a))
    for pos, g in zip(positions, fill):
        child[pos] = g
    return child  # type: ignore[return-value]


def mutate(perm: list[int], rng: random.Random) -> None:
    n = len(perm)
    if n < 2:
        return
    kind = rng.choice(("swap", "inversion", "relocate"))
    i, j = sorted(rng.sample(range(n), 2))
    if kind == "swap":
        perm[i], perm[j] = perm[j], perm[i]
    elif kind == "inversion":
        perm[i:j + 1] = reversed(perm[i:j + 1])
    else:
        perm.insert(j, perm.pop(i))


def _random_nn_tour(p: _Problem, rng: random.Random, k: int = 3) -> list[int]:
    left = set(range(1, p.n + 1))
    cur = rng.choice(sorted(left))
    tour = [cur]
    left.remove(cur)
    while left:
        cand = sorted(left, key=lambda c: p.d[cur][c])[:k]
        cur = rng.choice(cand)
        tour.append(cur)
        left.remove(cur)
    return tour


def _random_due_tour(p: _Problem, rng: random.Random) -> list[int]:
    """Customers ordered by due time with a little random jitter (time-window seed)."""
    span = max((x for x in p.due[1:] if x != float("inf")), default=1.0) or 1.0
    key = {c: (p.due[c] if p.due[c] != float("inf") else span) + rng.uniform(0, 0.05 * span)
           for c in range(1, p.n + 1)}
    return sorted(range(1, p.n + 1), key=key.__getitem__)


def solve_ga(instance: Instance, config: GAConfig | None = None,
             initial_tours: list[list[int]] | None = None) -> R.SolveResult:
    """initial_tours (customer ids) go into the start population; the hybrid uses this."""
    cfg = config or GAConfig()
    cfg_dict = asdict(cfg)

    def result(status, runtime, routes=None, message="", diag=None):
        return R.SolveResult(instance.instance_id, "ga", status, runtime, routes, cfg_dict,
                             seed=cfg.seed, message=message, diagnostics=diag or {})

    try:
        cfg.validate()
        instance.validate()
    except (InstanceValidationError, ValueError) as exc:
        return result(R.INVALID_INPUT, 0.0, message=str(exc))

    instance.distance_matrix()  # shared one-off cost, computed outside the timed region
    start = time.perf_counter()
    try:
        rng = random.Random(cfg.seed)
        p = _Problem(instance, cfg.lateness_weight)
        base = list(range(1, p.n + 1))
        deadline = None if cfg.time_limit_s is None else start + cfg.time_limit_s

        def out_of_time() -> bool:
            return deadline is not None and time.perf_counter() >= deadline

        pop: list[list[int]] = []
        index_of = instance.index_of() if initial_tours else {}
        for tour in (initial_tours or [])[:cfg.population_size]:
            perm = [index_of[c] for c in tour]
            if sorted(perm) != base:
                raise ValueError("initial tour must visit every customer exactly once")
            pop.append(perm)
        seeded = len(pop)
        n_nn = min(int(cfg.population_size * cfg.nn_seed_fraction), cfg.population_size - len(pop))
        pop.extend(_random_nn_tour(p, rng) for _ in range(n_nn))
        if p.tw:
            n_due = min(int(cfg.population_size * cfg.due_seed_fraction), cfg.population_size - len(pop))
            pop.extend(_random_due_tour(p, rng) for _ in range(n_due))
        repair_calls = repair_wins = fleet_calls = fleet_wins = ls_calls = ls_moves = 0
        while len(pop) < cfg.population_size:
            perm = base[:]
            rng.shuffle(perm)
            pop.append(perm)
        fit = [p.fitness(x) for x in pop]
        evaluations = len(pop)

        best_fit, best_perm = min(zip(fit, pop), key=lambda t: t[0])
        best_perm = best_perm[:]
        history = [best_fit]
        stagnant, stop_reason, gen = 0, "max_generations", 0

        for gen in range(1, cfg.max_generations + 1):
            if out_of_time():
                stop_reason = "time_limit"
                gen -= 1
                break
            order = sorted(range(len(pop)), key=fit.__getitem__)
            new_pop = [pop[i][:] for i in order[:cfg.elite_count]]
            new_fit = [fit[i] for i in order[:cfg.elite_count]]

            def tournament() -> list[int]:
                picks = [rng.randrange(len(pop)) for _ in range(cfg.tournament_size)]
                return pop[min(picks, key=fit.__getitem__)]

            cut_short = False
            while len(new_pop) < cfg.population_size:
                if out_of_time():  # stop mid-generation; every kept child is scored
                    cut_short = True
                    break
                p1, p2 = tournament(), tournament()
                child = order_crossover(p1, p2, rng) if rng.random() < cfg.crossover_rate else p1[:]
                if rng.random() < cfg.mutation_rate:
                    mutate(child, rng)
                if cfg.local_search and rng.random() < cfg.ls_rate:
                    _, rts = p.split(child)
                    rts, moves = local_search(p, rts, rng, deadline, cfg.ls_neighbours)
                    child = routes_to_tour(rts)
                    ls_calls += 1
                    ls_moves += moves
                new_pop.append(child)
                new_fit.append(p.fitness(child))
                evaluations += 1
            pop, fit = new_pop, new_fit

            gen_best = min(range(len(pop)), key=fit.__getitem__)
            if cfg.fleet_repair and not out_of_time():
                _, rts = p.split(pop[gen_best])
                if len(rts) > p.vehicles:
                    fleet_calls += 1
                    fixed = routes_to_tour(fleet_repair(p, rts, deadline))
                    fixed_fit = p.fitness(fixed)
                    evaluations += 1
                    if fixed_fit < fit[gen_best] - 1e-9:
                        fleet_wins += 1
                        worst = max(range(len(pop)), key=fit.__getitem__)
                        pop[worst], fit[worst] = fixed, fixed_fit
                        gen_best = worst
            if p.tw and cfg.tw_repair and not out_of_time() and _needs_repair(p, pop[gen_best]):
                repair_calls += 1
                fixed, fixed_fit, used = repair_time_windows(p, pop[gen_best], rng)
                evaluations += used
                if fixed_fit < fit[gen_best] - 1e-9:
                    repair_wins += 1
                    worst = max(range(len(pop)), key=fit.__getitem__)
                    pop[worst], fit[worst] = fixed, fixed_fit
                    gen_best = worst
            if fit[gen_best] < best_fit - 1e-12:
                best_fit, best_perm, stagnant = fit[gen_best], pop[gen_best][:], 0
            else:
                stagnant += 1
            history.append(best_fit)
            if cut_short:
                stop_reason = "time_limit"
                break
            if cfg.stagnation_generations is not None and stagnant >= cfg.stagnation_generations:
                stop_reason = "stagnation"
                break

        _, node_routes = p.split(best_perm)
        ids = instance.node_ids
        routes = [[ids[c] for c in r] for r in node_routes]
        # pad with empty routes so len(routes) == vehicle_count when possible
        routes += [[] for _ in range(max(0, instance.vehicle_count - len(routes)))]
        runtime = time.perf_counter() - start
        step = max(1, len(history) // 200)
        diag = {"generations_run": gen, "stop_reason": stop_reason, "evaluations": evaluations,
                "best_fitness": best_fit, "fitness_history": history[::step], "seeded_tours": seeded,
                "fleet_repair_calls": fleet_calls, "fleet_repair_improvements": fleet_wins,
                "local_search_calls": ls_calls, "local_search_moves": ls_moves}
        if p.tw:
            diag.update(repair_calls=repair_calls, repair_improvements=repair_wins,
                        best_lateness=sum(sum(p.route_lateness(r)) for r in node_routes))
        return result(R.SOLVED, runtime, routes, diag=diag)
    except Exception as exc:
        return result(R.ERROR, time.perf_counter() - start, message=f"{type(exc).__name__}: {exc}")
