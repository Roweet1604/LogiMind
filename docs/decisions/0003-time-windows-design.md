# 0003: Time windows (CVRPTW) design

Date: 2 Nov 2026. Status: accepted (P1).

## Decision
- **Model.** `Customer` gains `ready_time`, `due_time` (None = no limit) and `service_time`. `Instance` gains `depot_ready_time`, `depot_due_time`, `time_per_distance` (travel time = distance x this) and `time_unit`. Service must *start* inside the window; early arrival waits. With all defaults the instance is a plain CVRP, and its `instance_id` is byte-for-byte the baseline id (tested), so stored runs and the measured evidence stay linked.
- **Validator 1.1** recomputes each route's schedule from the instance alone (leave at depot ready time, start each service as early as allowed). It reports `time_window_violated` per late stop and `depot_return_late` per late route, with total lateness.
- **Metrics** add time-window violations (no longer counted as "other"), total lateness, total waiting and route durations.
- **OR-Tools.** Hard windows through a "Time" dimension. Integer scaling rounds travel and service UP, and due times DOWN, so every schedule OR-Tools accepts is also on time in exact arithmetic. "No solution" is reported as such.
- **GA: penalty plus repair.** The split decoder adds `lateness_weight x (stop lateness + late depot return)` to each route; capacity stays hard. By default one time unit late costs as much as the worst feasible plan, so on-time plans always win. Once per generation, while the best tour is late or needs more routes than vehicles, a repair move reinserts the latest customer (or one from the shortest route) at its best position. Part of the start population is ordered by due time. All of this runs inside the same wall-clock budget.

## Why
- Keeping old ids stable protects the Review 2 evidence.
- Conservative rounding keeps the invariant "no infeasible plan shown as success" without trusting the solver.
- Penalty plus repair is the standard way to keep the giant-tour + split GA a real search of its own (invariant 6).

## Consequences
- In a 5 s trial (one seed, this laptop), the plain GA keeps windows but uses far too many routes on Solomon instances. On R101 it ends infeasible (more routes than vehicles). P3 (local search, hybrid) addresses this; the numbers are not tuned and not for quoting.
- OR-Tools' baseline default (PATH_CHEAPEST_ARC) found no solution for R101 in 5 s, while PARALLEL_CHEAPEST_INSERTION and SAVINGS did. P2's audit must cover time-window instances separately.
- Known baseline quirk kept on purpose: the id hashes coordinates as given, so `10` and `10.0` give different ids. The API always sends floats.
