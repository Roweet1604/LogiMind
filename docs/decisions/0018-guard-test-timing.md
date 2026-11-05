# 0018: Timing margins of the wall-clock guard test

Date: 5 Nov 2026 (unattended session)

## Problem
`tests/test_hybrid.py::test_guard_stops_a_frozen_run_and_reports_a_timeout` failed once in a full run (4 Nov 2026) and passed in every rerun. It asserted `1.4 <= waited < 10` s, where `waited` was measured around `worker.run(...)`.

## Cause (measured)
`worker.run` first spawns the worker process if none is running. The spawned process imports the solvers, and the test module (FastAPI, OR-Tools, LangGraph, ...). Measured on Rohit's laptop, idle, 5 Nov 2026: **5.8 s, 6.4 s, 5.9 s** per spawn. So `waited` was about 6 s spawn + 1.5 s hard limit = 7.5 s against a 10 s cap; a busy laptop pushes the spawn past 8.5 s and the test fails. The spawn is not part of what the guard measures (the guard's own clock starts after it), so the test measured the wrong interval.

## Decision
- Start the worker (`_ensure_worker`) before starting the clock.
- Lower bound: the guard's own hard limit (`diagnostics.hard_limit_s == 1.5`), with 0.05 s allowance for the OS timer, instead of a loose 1.4 s.
- Upper bound: 30 s. It still proves that the run was stopped by the guard and did not wait for the frozen solver (which sleeps 60 s and then raises).
- New assertion: the frozen worker process is really dead afterwards (`not proc.is_alive()`).

The test proves at least as much as before (a tighter lower bound and a kill check were added); only the upper bound grew, and it stays far below the solver's 60 s.

## Verification
10 consecutive runs of the test alone: 10 passed (5 Nov 2026). Full suite afterwards: see PROGRESS.md.
