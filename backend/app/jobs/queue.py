"""Durable job queue in the database (P6, decision 0021).

* `enqueue` adds a Job row in the caller's session, so a plan and its job are committed together.
* `claim` hands the oldest queued job to a worker (FIFO over both lanes). Every claim first updates the
  single `queue_lock` row, which serializes claims on SQLite and PostgreSQL alike. Lane rules:
  - a **benchmark** job starts only when no other job is running, and while it runs nothing else starts
    (fair timing: one benchmark job at a time, alone on the machine as far as the queue can control);
  - **planning** jobs (plan, replan) may run side by side when several workers run.
  FIFO means a waiting benchmark job is not overtaken by later planning jobs.
* A running job's worker sends a heartbeat. `recover_stale` requeues a job whose heartbeat is older than
  `stale_s` (the worker crashed or was killed), up to `max_attempts` claims in total; after that the job
  is failed with the reason, and the caller marks its plan failed.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Job, QueueLock, utcnow

LANES = {"plan": "planning", "replan": "planning", "benchmark": "benchmark"}
TERMINAL = ("completed", "failed")
DEFAULT_STALE_S = 30.0
DEFAULT_MAX_ATTEMPTS = 2


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; every time here is UTC."""
    return None if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class JobView:
    """A detached snapshot of a job (safe to pass between threads)."""
    id: str
    kind: str
    lane: str
    tenant_id: str | None
    plan_id: str | None
    payload: dict[str, Any]
    state: str
    attempts: int
    max_attempts: int
    worker_id: str | None
    result: dict[str, Any] | None
    error: str | None
    history: list | None
    created_at: datetime | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, j: Job) -> "JobView":
        return cls(j.id, j.kind, j.lane, j.tenant_id, j.plan_id, dict(j.payload or {}), j.state, j.attempts or 0,
                   j.max_attempts or DEFAULT_MAX_ATTEMPTS, j.worker_id, j.result, j.error, j.history,
                   aware(j.created_at), aware(j.started_at), aware(j.heartbeat_at), aware(j.finished_at))

    def public(self) -> dict[str, Any]:
        """What a tenant may see about its own plan's job."""
        def iso(d: datetime | None) -> str | None:
            return d.isoformat() if d else None

        return {"job_id": self.id, "kind": self.kind, "state": self.state, "attempts": self.attempts,
                "max_attempts": self.max_attempts, "worker_id": self.worker_id, "error": self.error,
                "requeues": self.history or [], "created_at": iso(self.created_at),
                "started_at": iso(self.started_at), "finished_at": iso(self.finished_at)}


class JobQueue:
    def __init__(self, factory: sessionmaker[Session], stale_s: float = DEFAULT_STALE_S,
                 clock: Callable[[], datetime] = utcnow):
        self.factory, self.stale_s, self.clock = factory, stale_s, clock
        self._listeners: list[threading.Event] = []
        with factory() as s:  # tables made by create_all (tests) have no lock row yet
            if s.get(QueueLock, 1) is None:
                s.add(QueueLock(id=1, claims=0))
                s.commit()

    # ---- producers --------------------------------------------------------------------------
    def enqueue(self, s: Session, kind: str, payload: dict[str, Any], tenant_id: str | None = None,
                plan_id: str | None = None, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> str:
        if kind not in LANES:
            raise ValueError(f"unknown job kind {kind!r}")
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        s.add(Job(id=job_id, kind=kind, lane=LANES[kind], tenant_id=tenant_id, plan_id=plan_id, payload=payload,
                  state="queued", attempts=0, max_attempts=max_attempts, created_at=self.clock()))
        return job_id

    def listen(self, event: threading.Event) -> None:
        """An in-process worker wakes up as soon as something is queued here (no polling delay)."""
        self._listeners.append(event)

    def notify(self) -> None:
        for e in self._listeners:
            e.set()

    # ---- workers ----------------------------------------------------------------------------
    def _lock(self, s: Session) -> None:
        s.execute(update(QueueLock).where(QueueLock.id == 1).values(claims=QueueLock.claims + 1))

    def claim(self, worker_id: str) -> JobView | None:
        with self.factory() as s:
            self._lock(s)
            running = set(s.scalars(select(Job.lane).where(Job.state == "running")))
            job = s.scalars(select(Job).where(Job.state == "queued")
                            .order_by(Job.created_at, Job.id).limit(1)).first()
            if job is None or "benchmark" in running or (job.lane == "benchmark" and running):
                s.commit()
                return None
            now = self.clock()
            job.state, job.worker_id, job.attempts = "running", worker_id, (job.attempts or 0) + 1
            job.started_at = job.heartbeat_at = now
            job.error = None
            s.commit()
            return JobView.of(job)

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        """False when the job is no longer this worker's (it was requeued after a stale heartbeat)."""
        with self.factory() as s:
            n = s.execute(update(Job).where(Job.id == job_id, Job.worker_id == worker_id, Job.state == "running")
                          .values(heartbeat_at=self.clock())).rowcount
            s.commit()
            return n == 1

    def finish(self, job_id: str, worker_id: str, state: str, result: dict | None = None,
               error: str | None = None) -> bool:
        if state not in TERMINAL:
            raise ValueError(state)
        with self.factory() as s:
            n = s.execute(update(Job).where(Job.id == job_id, Job.worker_id == worker_id, Job.state == "running")
                          .values(state=state, result=result, error=error, finished_at=self.clock())).rowcount
            s.commit()
            return n == 1

    def recover_stale(self) -> list[JobView]:
        """Requeue (or fail, after max_attempts) running jobs whose worker stopped sending heartbeats.
        Returns the jobs that were FAILED, so the caller can mark their plans failed and notify."""
        cutoff = self.clock() - timedelta(seconds=self.stale_s)
        failed: list[JobView] = []
        with self.factory() as s:
            self._lock(s)
            stale = s.scalars(select(Job).where(Job.state == "running", Job.heartbeat_at < cutoff)).all()
            for job in stale:
                note = {"at": self.clock().isoformat(timespec="seconds"), "worker_id": job.worker_id,
                        "attempt": job.attempts, "reason": f"no heartbeat for more than {self.stale_s:g} s"}
                job.history = [*(job.history or []), note]
                if (job.attempts or 0) < (job.max_attempts or DEFAULT_MAX_ATTEMPTS):
                    job.state, job.worker_id = "queued", None
                else:
                    job.state, job.finished_at = "failed", self.clock()
                    job.error = (f"the worker stopped during the job {job.attempts} time(s) "
                                 f"(no heartbeat for more than {self.stale_s:g} s); not retried again")
                    failed.append(JobView.of(job))
            s.commit()
        if len(failed) < len(stale):
            self.notify()
        return failed

    # ---- readers ----------------------------------------------------------------------------
    def get(self, job_id: str) -> JobView | None:
        with self.factory() as s:
            j = s.get(Job, job_id)
            return JobView.of(j) if j else None

    def for_plan(self, plan_id: str, tenant_id: str) -> JobView | None:
        """A tenant's own plan's job: filtered by tenant explicitly (jobs are not TenantOwned)."""
        with self.factory() as s:
            j = s.scalars(select(Job).where(Job.plan_id == plan_id, Job.tenant_id == tenant_id)
                          .order_by(Job.created_at.desc())).first()
            return JobView.of(j) if j else None

    def stats(self) -> dict[str, Any]:
        with self.factory() as s:
            rows = s.execute(select(Job.state, Job.heartbeat_at).where(Job.state.in_(("queued", "running")))).all()
            last = s.scalars(select(Job.heartbeat_at).where(Job.heartbeat_at.is_not(None))
                             .order_by(Job.heartbeat_at.desc()).limit(1)).first()
        return {"queued": sum(r[0] == "queued" for r in rows), "running": sum(r[0] == "running" for r in rows),
                "last_heartbeat_at": aware(last).isoformat(timespec="seconds") if last else None}
