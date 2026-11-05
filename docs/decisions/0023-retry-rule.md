# 0023: Retry rule for failed deliveries

Date: 5 Nov 2026 (unattended session)

## Problem
In the browser check of 5 Nov 2026, a failed delivery with `retry=true` was planned again as the very next stop. The replan does not model the failed attempt itself (the vehicle is assumed to be at its last completed stop), so going straight back is often the cheapest plan, although it is rarely useful (the customer was just not there).

## Decision
- **Rule:** a retried stop is never a route's next unfinished stop (the stop right after the completed prefix, or the first stop after the depot), **unless it is that route's only remaining stop**, in which case it is at the end of the route.
- **OR-Tools:** for every vehicle that is not blocked, a hard constraint `next(last done) != retry OR next(retry) == end` (`not_next` in `solve_ortools`).
- **Warm start:** the cheapest insertion skips positions that break the rule.
- **Independent check:** `check_replan` reports a too-early retry, so such a plan can never be stored as feasible (the same pattern as frozen stops).
- **GA:** refused for retries (`422`), because its giant-tour encoding cannot express the rule (as for frozen stops).
- No minimum time delay: plans without time windows have no clock to measure it against. A time-based rule ("not before 30 minutes") is possible later on time-window plans.

## Effect on stored results
The replanning experiment (`experiments/results/replan_2026-11-04/`) ran before this rule; its failed-delivery numbers are for the old behaviour and are labelled so in the report. Tests: 3 new in `tests/test_replan.py`; one shows that without the rule OR-Tools retries at once on the test instance, and with it does not.
