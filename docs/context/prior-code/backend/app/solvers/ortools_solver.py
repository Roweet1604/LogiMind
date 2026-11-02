"""OR-Tools CVRP baseline.

Objective matches the shared cost model exactly: arc cost = cost_per_distance *
distance, fixed cost per used vehicle = fixed_vehicle_cost. OR-Tools needs
integers, so costs are scaled by SCALE (x1000) and rounded; the reported
distance is nevertheless recomputed from the float matrix by the shared
evaluator, never read from OR-Tools.

Default search: PATH_CHEAPEST_ARC first solution + GUIDED_LOCAL_SEARCH,
stopped by a wall-clock limit (GLS never stops on its own).

Time budget: `time_limit_s` is the TOTAL wall-clock budget of the run. OR-Tools'
own limit only covers its search, so the model-build time (arc-cost table,
callbacks) is measured and subtracted: search_limit = budget - build_time
(never below MIN_SEARCH_S). This keeps the clock equal to the GA's, whose limit
also includes its set-up. Both values are recorded in the run diagnostics.
"""
from __future__ import annotations

import time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.models import result as R
from app.models.problem import Instance, InstanceValidationError

SCALE = 1000
MIN_SEARCH_S = 0.05
ROUTING_STATUS = {
    0: "NOT_SOLVED", 1: "SUCCESS", 2: "PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED",
    3: "FAIL", 4: "FAIL_TIMEOUT", 5: "INVALID", 6: "INFEASIBLE", 7: "OPTIMAL",
}


def solve_ortools(
    instance: Instance,
    time_limit_s: float = 10.0,
    first_solution: str = "PATH_CHEAPEST_ARC",
    metaheuristic: str = "GUIDED_LOCAL_SEARCH",
) -> R.SolveResult:
    config = {"time_limit_s": time_limit_s, "first_solution_strategy": first_solution,
              "local_search_metaheuristic": metaheuristic, "cost_scale": SCALE}

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

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = getattr(routing_enums_pb2.FirstSolutionStrategy, first_solution)
        params.local_search_metaheuristic = getattr(routing_enums_pb2.LocalSearchMetaheuristic, metaheuristic)
        build_s = time.perf_counter() - start
        search_limit_s = max(MIN_SEARCH_S, time_limit_s - build_s)
        params.time_limit.FromMilliseconds(max(1, int(search_limit_s * 1000)))

        solution = routing.SolveWithParameters(params)
        status_name = ROUTING_STATUS.get(routing.status(), str(routing.status()))
        if solution is None:
            runtime = time.perf_counter() - start
            st = R.TIMEOUT_NO_SOLUTION if status_name == "FAIL_TIMEOUT" else R.NO_SOLUTION
            return result(st, runtime, message=f"OR-Tools returned no solution ({status_name})",
                          diag={"ortools_status": status_name, "build_seconds": round(build_s, 4),
                                "search_limit_s": round(search_limit_s, 4)})

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
            "build_seconds": round(build_s, 4), "search_limit_s": round(search_limit_s, 4)})
    except Exception as exc:  # surfaced explicitly, never converted into a fake success
        return result(R.ERROR, time.perf_counter() - start, message=f"{type(exc).__name__}: {exc}")
