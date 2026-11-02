"""Hard wall-clock guard for solver runs (P3).

The solvers stop themselves at their time limit, but a run can still hang
(native code, a frozen machine: the P2 audit had one 10 s run take 1506 s).
A Python thread cannot be stopped, so runs execute in one long-lived worker
PROCESS. If a run has not answered within

    hard_limit = factor x time_limit + grace_s

the worker is killed, the run is reported as `hard_timeout` (never as a
success, with no routes), and a fresh worker is started for the next run.

The worker imports the solvers once at start-up; that start-up time is not
charged to any run. Runs still go one at a time (the caller is single-threaded).
"""
from __future__ import annotations

import multiprocessing as mp
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.models import result as R
from app.models.problem import Instance
from app.services.runner import RunRecord, run_algorithm

DEFAULT_FACTOR = 1.5
DEFAULT_GRACE_S = 5.0
DEFAULT_BUDGET_S = 300.0  # used when a run has no time limit (GA stopped by generations only)


def _worker_main(conn, target: Callable[..., RunRecord]) -> None:
    conn.send(("ready", None))
    while True:
        try:
            job = conn.recv()
        except EOFError:
            return
        if job is None:
            return
        instance, algorithm, config = job
        try:
            conn.send(("ok", target(instance, algorithm, config)))
        except Exception as exc:  # reported to the caller, never hidden
            conn.send(("error", f"{type(exc).__name__}: {exc}"))


class GuardedWorker:
    def __init__(self, target: Callable[..., RunRecord] = run_algorithm, factor: float = DEFAULT_FACTOR,
                 grace_s: float = DEFAULT_GRACE_S, default_budget_s: float = DEFAULT_BUDGET_S,
                 ready_timeout_s: float = 120.0):
        self.target, self.factor, self.grace_s = target, factor, grace_s
        self.default_budget_s, self.ready_timeout_s = default_budget_s, ready_timeout_s
        self._proc = self._conn = None
        self.restarts = 0

    def _ensure_worker(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            return
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe()
        proc = ctx.Process(target=_worker_main, args=(child, self.target), daemon=True, name="solver-worker")
        proc.start()
        child.close()
        if not parent.poll(self.ready_timeout_s):
            proc.kill()
            raise RuntimeError("solver worker did not start")
        parent.recv()
        self._proc, self._conn = proc, parent

    def hard_limit(self, config: dict[str, Any]) -> float:
        budget = config.get("time_limit_s") or self.default_budget_s
        return self.factor * float(budget) + self.grace_s

    def _kill(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc.join(timeout=10)
        self._proc = self._conn = None

    def run(self, instance: Instance, algorithm: str, config: dict[str, Any] | None = None) -> RunRecord:
        config = dict(config or {})
        self._ensure_worker()
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        limit = self.hard_limit(config)
        t0 = time.perf_counter()
        try:
            self._conn.send((instance, algorithm, config))
            answered = self._conn.poll(limit)
        except (OSError, EOFError, BrokenPipeError):
            answered = False
        if not answered:
            elapsed = time.perf_counter() - t0
            self._kill()
            self.restarts += 1
            res = R.SolveResult(instance.instance_id, algorithm, R.HARD_TIMEOUT, elapsed, None, config,
                                seed=config.get("seed"),
                                message=f"stopped by the wall-clock guard after {elapsed:.1f} s "
                                        f"(hard limit {limit:.1f} s = {self.factor} x time limit + {self.grace_s} s)",
                                diagnostics={"hard_limit_s": round(limit, 3)})
            return RunRecord(instance, res, None, None, started)
        try:
            kind, payload = self._conn.recv()
        except EOFError:  # worker died while answering
            self._kill()
            raise RuntimeError("solver worker crashed")
        if kind == "error":
            raise RuntimeError(payload)
        return payload

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.send(None)
            except (OSError, BrokenPipeError):
                pass
        if self._proc is not None:
            self._proc.join(timeout=5)
            if self._proc.is_alive():
                self._proc.kill()
        self._proc = self._conn = None
