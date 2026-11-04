# 0012: Replanning (P7)

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Decision
- **Endpoint:** `POST /api/plans/{plan_id}/replan` (API key, tenant-scoped). The body has `event`, `engine` ("ortools" default, or "ga"), `time_limit_s` (default 5), `warm_start` (default true) and `seed`. The result is a new plan whose `parent_plan_id` points at the old one. Only a completed, feasible plan can be replanned (otherwise 409). An event that does not fit the plan gives 422. Another tenant's plan gives 404. Webhook event: `plan.replanned`. Migration 0003 adds `parent_id`, `event` and `replan` to `plans`.
- **Events** (`app/replan/events.py`): `vehicle_breakdown` {vehicle}, `failed_delivery` {customer_id, retry}, `urgent_order` {customer}. Each also takes `completed` (vehicle -> number of stops done) and `now` (time-window instances).
- **Frozen stops:** the completed prefix of each route. **Assumption:** completed stops were served on the planned (earliest) schedule.
- **Broken vehicle:** gets no further stops; its route ends after its completed stops (the return leg is still counted).
- **Failed delivery:** with `retry`, the customer is visited again later. Without it, the customer is removed from the instance and listed in `dropped_customers`. The failed attempt's own travel is not modelled.
- **Current time `now`:** every unfinished stop gets `ready = max(ready, now)` in a timing copy of the instance. The solver works on that copy, and the copy is validated too. A customer whose due time is already past gives 422, and the message says how to drop it.
- **OR-Tools:** frozen prefixes become hard `NextVar` chains from `Start(v)` plus `ApplyLocksToAllVehicles` (a partial first solution). A broken vehicle's `VehicleVar` loses its index for every unfinished stop. For the warm start, the current plan is adjusted to the event (unfinished stops of a broken vehicle and new or retried customers go in by cheapest feasible insertion), then given to `ReadAssignmentFromRoutes`. If OR-Tools rejects it, or no complete adjusted plan exists, the search starts cold and the plan says so (`warm_start` / `warm_start_result`).
- **Finding:** SAVINGS, the audited CVRP default for short budgets, found **no** first solution with frozen prefixes or blocked vehicles on every instance we tried. PATH_CHEAPEST_ARC, LOCAL/PARALLEL_CHEAPEST_INSERTION and CHRISTOFIDES all worked. So in a replan an *audited* SAVINGS default is replaced by PARALLEL_CHEAPEST_INSERTION, and `search_choice` records this. An explicitly requested SAVINGS is kept.
- **GA:** seeded with the adjusted current plan (`initial_tours`), and allowed **only when no stop is frozen**. Its giant-tour + split encoding cannot pin a prefix to a vehicle. A broken vehicle with no completed stops just shrinks the fleet, since vehicles are identical. With frozen stops, `engine=ga` gives 422 with that reason. Open item: frozen prefixes in the GA.
- **Acceptance:** a replanned plan is `feasible` only if the validator passes on the real post-event instance **and** the independent check (`check_replan`) passes: frozen prefixes unchanged, broken vehicle idle, no extra routes, and on time with `now` applied. Otherwise it is stored and shown as infeasible (tested with a fleet that cannot absorb a breakdown).
- **Timing:** `replan.timing.disruption_to_feasible_s` runs from receiving the replan request to the validated plan, including queue wait, solver and validation; it is null if the plan is not feasible. Also stored: solver seconds and OR-Tools' time to its first solution.

## Evidence
`experiments/results/replan_2026-11-04/report.md` (96 synthetic replans, 2.1 min): all feasible; warm start better at 0.5 s, no clear difference at 2 s (slightly worse for breakdowns).

## Note on a test run
The first full run of `tests/test_replan.py`, with the earlier `solver.Add`-only freeze and SAVINGS, failed 4 tests and took 82 min of wall-clock time. Each test re-run alone takes 3 to 9 s, and the whole file 27 s. A direct check of SAVINGS with frozen stops returned in 0.5 s, so the cause of the long run was not found. The laptop may have gone to sleep: a similar clock jump happened in the previous session. Test runs now use `timeout`.
