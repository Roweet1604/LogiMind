# 0037: Replans keep earlier disruptions

Date: 11 Nov 2026. Status: accepted (asked for by the team; next step 6 in PROGRESS.md).

## Problem
`apply_event` only looked at the new event. Replanning a replanned plan forgot the earlier disruptions: a vehicle
that broke down could get new stops, completed stops the client did not repeat could be moved, and a retried
delivery lost the retry rule (decision 0023).

## Decision
- `apply_event(instance, routes, event, earlier)` takes the parent plan's replan record (`earlier`; empty for a
  first replan) and carries it forward:
  - **blocked:** the parent's broken vehicles stay blocked; a new breakdown is added. A breakdown of a vehicle that
    is already blocked is refused (422).
  - **frozen:** per vehicle the larger of the client's `completed` count and the parent's frozen count. A client can
    add completed stops but cannot un-complete them.
  - **retry:** the parent's retried customers keep the rule until they are completed (frozen) or dropped
    (`failed_delivery`, `retry=false`). A new failed delivery of a retried customer replaces its entry.
- Every carried item is said in the plan's notes ("... from the earlier replan").
- The replan record now stores `retry` with `frozen` and `blocked`, so the next replan can read it. Older replanned
  plans have no `retry` key and are read as having none.
- The independent check (`check_replan`) is unchanged; it already checks the merged frozen, blocked and retry lists,
  so a solver that ignores them cannot get a plan stored as feasible.

## Tests
`backend/tests/test_replan_chain.py`: a second replan keeps the broken vehicle and its completed stops, keeps
completed stops the client forgot, and keeps the retry rule.
