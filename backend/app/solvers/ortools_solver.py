"""OR-Tools CVRP baseline.

Objective matches the shared cost model exactly: arc cost = cost_per_distance *
distance, fixed cost per used vehicle = fixed_vehicle_cost. OR-Tools needs
integers, so costs are scaled by SCALE (x1000) and rounded; the reported
distance is nevertheless recomputed from the float matrix by the shared
evaluator, never read from OR-Tools.

Default search: chosen per problem type (CVRP / VRPTW) and budget class from
the P2 audit (AUDITED_DEFAULTS, docs/decisions/0005). An explicit
first_solution / metaheuristic always wins. Time-bound metaheuristics never
stop on their own; the wall-clock limit stops them.

Time budget: `time_limit_s` is the TOTAL wall-clock budget of the run. OR-Tools'
own limit only covers its search, so the model-build time (arc-cost table,
callbacks) is measured and subtracted: search_limit = budget - build_time
(never below MIN_SEARCH_S). This keeps the clock equal to the GA's, whose limit
also includes its set-up. Both values are recorded in the run diagnostics.
"""
from __future__ import annotations

import math
import time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.models import result as R
from app.models.problem import Instance, InstanceValidationError

SCALE = 1000
TIME_SCALE = 1000
MIN_SEARCH_S = 0.05
ROUTING_STATUS = {
    0: "NOT_SOLVED", 1: "SUCCESS", 2: "PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED",
    3: "FAIL", 4: "FAIL_TIMEOUT", 5: "INVALID", 6: "INFEASIBLE", 7: "OPTIMAL",
}
# Budget classes (upper bound in seconds, inclusive) used for the audited defaults.
BUDGET_CLASSES = [("short", 2.0), ("medium", 6.0), ("long", math.inf)]


def budget_class(budget_s: float) -> str:
    for name, upper in BUDGET_CLASSES:
        if budget_s <= upper:
            return name
    raise AssertionError("unreachable")


# Winners of the P2 audit (experiments/results/ortools_audit_2026-11-02, decision 0005):
# per (problem, budget class), the configuration that solved every run with the lowest
# mean gap. Evidence: n <= 100 customers, budgets 1 / 3 / 10 s, one laptop. Budgets above
# 10 s use the "long" entry without having been tested there.
AUDITED_DEFAULTS = {
    ("CVRP", "short"): ("SAVINGS", "GUIDED_LOCAL_SEARCH"),
    ("CVRP", "medium"): ("SAVINGS", "GUIDED_LOCAL_SEARCH"),
    ("CVRP", "long"): ("PATH_CHEAPEST_ARC", "GUIDED_LOCAL_SEARCH"),
    ("VRPTW", "short"): ("PARALLEL_CHEAPEST_INSERTION", "TABU_SEARCH"),
    ("VRPTW", "medium"): ("PARALLEL_CHEAPEST_INSERTION", "TABU_SEARCH"),
    ("VRPTW", "long"): ("LOCAL_CHEAPEST_INSERTION", "GUIDED_LOCAL_SEARCH"),
}


def default_search(has_time_windows: bool, time_limit_s: float) -> tuple[str, str]:
    return AUDITED_DEFAULTS[("VRPTW" if has_time_windows else "CVRP", budget_class(time_limit_s))]


def _up(v: float) -> int:
    """Scale up and round up, ignoring float noise (12.3 * 1000 = 12300.000000000002)."""
    return math.ceil(v * TIME_SCALE - 1e-6)


def _down(v: float) -> int:
    return math.floor(v * TIME_SCALE + 1e-6)


def _add_time_dimension(instance: Instance, manager, routing) -> None:
    """Hard time windows as an OR-Tools "Time" dimension.

    OR-Tools needs integers, so times are scaled by TIME_SCALE and rounded
    conservatively: travel + service times UP, due times DOWN. Any schedule
    OR-Tools accepts is therefore also on time with the exact float times the
    validator uses; the price is a slightly tighter problem.
    """
    t = instance.travel_time_matrix()
    service = instance.service_times
    n = len(t)
    transit = [[_up(service[i] + t[i][j]) for j in range(n)] for i in range(n)]

    def time_cost(from_index: int, to_index: int) -> int:
        return transit[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    ready, due = instance.ready_times, instance.due_times
    if math.isfinite(due[0]):
        horizon = _down(due[0])
    else:  # no depot limit: any route fits within ready + all services + all longest arcs
        horizon = _up(ready[0]) + sum(max(row) for row in transit) + 1
    time_cb = routing.RegisterTransitCallback(time_cost)
    # slack = waiting allowed at a node; fix_start_cumul_to_zero=False so routes may start later.
    routing.AddDimension(time_cb, horizon, horizon, False, "Time")
    dim = routing.GetDimensionOrDie("Time")
    for node in range(1, n):
        lo = _up(ready[node])
        hi = horizon if not math.isfinite(due[node]) else min(horizon, _down(due[node]))
        dim.CumulVar(manager.NodeToIndex(node)).SetRange(lo, hi)
    depot_lo = _up(ready[0])
    for v in range(instance.vehicle_count):
        dim.CumulVar(routing.Start(v)).SetRange(depot_lo, horizon)
        dim.CumulVar(routing.End(v)).SetRange(depot_lo, horizon)
        routing.AddVariableMinimizedByFinalizer(dim.CumulVar(routing.Start(v)))
        routing.AddVariableMinimizedByFinalizer(dim.CumulVar(routing.End(v)))


def solve_ortools(
    instance: Instance,
    time_limit_s: float = 10.0,
    first_solution: str | None = None,
    metaheuristic: str | None = None,
    frozen: list[list[int]] | None = None,
    blocked: list[int] | None = None,
    initial_routes: list[list[int]] | None = None,
) -> R.SolveResult:
    """first_solution / metaheuristic = None means: use the audited default for this
    problem type and budget class. The config records which choice was made.

    Replanning (P7) options, all customer ids:
    * frozen[v]: stops vehicle v has already completed; they stay its first stops, in order.
    * blocked: vehicles that get no further stops (breakdown); their route ends after frozen[v].
    * initial_routes[v]: warm start. Read with ReadAssignmentFromRoutes; if OR-Tools rejects them
      (not feasible for the model), the search starts cold and the diagnostics say so.
    (The current time of a replan is applied by the caller as a later ready time, app/replan/events.py.)
    With any of them set, the time of the first solution found is also recorded."""
    explicit = (first_solution is not None, metaheuristic is not None)
    default_fs, default_mh = default_search(instance.has_time_windows, time_limit_s)
    first_solution = first_solution or default_fs
    metaheuristic = metaheuristic or default_mh
    config = {"time_limit_s": time_limit_s, "first_solution_strategy": first_solution,
              "local_search_metaheuristic": metaheuristic, "cost_scale": SCALE,
              "time_windows": instance.has_time_windows, "budget_class": budget_class(time_limit_s),
              "search_choice": {(True, True): "explicit", (False, False): "audited_default"}.get(
                  explicit, "partly_audited_default")}
    if instance.has_time_windows:
        config["time_scale"] = TIME_SCALE
    replanning = any(x is not None for x in (frozen, blocked, initial_routes))
    if (frozen and any(frozen) or blocked) and first_solution == "SAVINGS" and not explicit[0]:
        # P7 finding: SAVINGS found no first solution with frozen prefixes or blocked vehicles on every
        # instance we tried; the insertion heuristics extend the locked routes (decision 0012).
        first_solution = config["first_solution_strategy"] = "PARALLEL_CHEAPEST_INSERTION"
        config["search_choice"] = "replan_override: SAVINGS -> PARALLEL_CHEAPEST_INSERTION"
    if replanning:
        config["replan"] = {"frozen_stops": sum(len(f) for f in frozen or []), "blocked": sorted(blocked or []),
                            "warm_start_given": initial_routes is not None}

    def result(status: str, runtime: float, routes=None, message="", diag=None) -> R.SolveResult:
        return R.SolveResult(instance.instance_id, "ortools", status, runtime, routes, config,
                             seed=None, message=message, diagnostics=diag or {})

    try:
        instance.validate()
    except InstanceValidationError as exc:
        return result(R.INVALID_INPUT, 0.0, message=str(exc))

    try:
        matrix = instance.distance_matrix()  # shared one-off cost, computed outside the timed region
    except Exception as exc:
        return result(R.ERROR, 0.0, message=f"{type(exc).__name__}: {exc}")

    start = time.perf_counter()
    try:
        n = len(matrix)
        manager = pywrapcp.RoutingIndexManager(n, instance.vehicle_count, 0)
        routing = pywrapcp.RoutingModel(manager)

        arc = [[int(round(instance.cost_per_distance * matrix[i][j] * SCALE)) for j in range(n)] for i in range(n)]

        def arc_cost(from_index: int, to_index: int) -> int:
            return arc[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

        transit = routing.RegisterTransitCallback(arc_cost)
        routing.SetArcCostEvaluatorOfAllVehicles(transit)
        routing.SetFixedCostOfAllVehicles(int(round(instance.fixed_vehicle_cost * SCALE)))

        demands = instance.demands
        demand_cb = routing.RegisterUnaryTransitCallback(lambda i: demands[manager.IndexToNode(i)])
        routing.AddDimensionWithVehicleCapacity(
            demand_cb, 0, [instance.vehicle_capacity] * instance.vehicle_count, True, "Capacity")

        if instance.has_time_windows:
            _add_time_dimension(instance, manager, routing)

        idx_of = instance.index_of()
        if frozen or blocked:
            solver = routing.solver()
            for v in range(instance.vehicle_count):
                prev = routing.Start(v)
                for cid in (frozen[v] if frozen and v < len(frozen) else []):
                    node_index = manager.NodeToIndex(idx_of[cid])
                    # Chained from Start(v), so the stop stays on vehicle v.
                    solver.Add(routing.NextVar(prev) == node_index)
                    prev = node_index
                if blocked and v in blocked:
                    solver.Add(routing.NextVar(prev) == routing.End(v))
            frozen_ids = {c for f in frozen or [] for c in f}
            for v in blocked or []:  # a broken vehicle may not take any unfinished stop
                for c in instance.customers:
                    if c.id not in frozen_ids:
                        routing.VehicleVar(manager.NodeToIndex(idx_of[c.id])).RemoveValue(v)
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = getattr(routing_enums_pb2.FirstSolutionStrategy, first_solution)
        params.local_search_metaheuristic = getattr(routing_enums_pb2.LocalSearchMetaheuristic, metaheuristic)
        first_found: list[float] = []
        if replanning:
            routing.AddAtSolutionCallback(lambda: first_found or first_found.append(time.perf_counter() - start))
        build_s = time.perf_counter() - start
        search_limit_s = max(MIN_SEARCH_S, time_limit_s - build_s)
        params.time_limit.FromMilliseconds(max(1, int(search_limit_s * 1000)))

        def replan_diag_base() -> dict:
            return {"warm_start": "not given", "first_solution_s": None}

        warm = None
        if frozen and any(frozen):
            # Hard constraints above keep the frozen stops; the locks also hand them to the first-solution
            # heuristic as a partial plan (without them the heuristics often found nothing).
            routing.CloseModelWithParameters(params)
            locks = [[manager.NodeToIndex(idx_of[c]) for c in (frozen[v] if v < len(frozen) else [])]
                     for v in range(instance.vehicle_count)]
            if not routing.ApplyLocksToAllVehicles(locks, False):
                return result(R.INVALID_INPUT, time.perf_counter() - start,
                              message="frozen stops do not form valid route prefixes", diag=replan_diag_base())
        if initial_routes is not None:
            routing.CloseModelWithParameters(params)
            nodes = [[idx_of[c] for c in r] for r in initial_routes]
            nodes += [[] for _ in range(instance.vehicle_count - len(nodes))]
            assignment = routing.ReadAssignmentFromRoutes(nodes, True)
            warm = "used" if assignment is not None else "rejected: initial routes not feasible for the model"
            solution = (routing.SolveFromAssignmentWithParameters(assignment, params) if assignment is not None
                        else routing.SolveWithParameters(params))
        else:
            solution = routing.SolveWithParameters(params)
        status_name = ROUTING_STATUS.get(routing.status(), str(routing.status()))
        replan_diag = ({"warm_start": warm or "not given",
                        "first_solution_s": round(first_found[0], 4) if first_found else None}
                       if replanning else {})
        if solution is None:
            runtime = time.perf_counter() - start
            st = R.TIMEOUT_NO_SOLUTION if status_name == "FAIL_TIMEOUT" else R.NO_SOLUTION
            return result(st, runtime, message=f"OR-Tools returned no solution ({status_name})",
                          diag={"ortools_status": status_name, "build_seconds": round(build_s, 4),
                                "search_limit_s": round(search_limit_s, 4), **replan_diag})

        routes: list[list[int]] = []
        ids = instance.node_ids
        for v in range(instance.vehicle_count):
            index, stops = routing.Start(v), []
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node != 0:
                    stops.append(ids[node])
                index = solution.Value(routing.NextVar(index))
            routes.append(stops)
        runtime = time.perf_counter() - start
        return result(R.SOLVED, runtime, routes, diag={
            "ortools_status": status_name, "solver_objective_scaled": solution.ObjectiveValue(),
            "build_seconds": round(build_s, 4), "search_limit_s": round(search_limit_s, 4), **replan_diag})
    except Exception as exc:  # surfaced explicitly, never converted into a fake success
        return result(R.ERROR, time.perf_counter() - start, message=f"{type(exc).__name__}: {exc}")
