"""P6 durable job queue (decision 0021): claim rules, heartbeats, crash recovery, the hard-timeout guard,
tenant isolation and webhooks through the queue, and real worker PROCESSES (crash + restart)."""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.db.keys import create_tenant, issue_key
from app.db.models import AuditLog, Job, Plan
from app.db.session import admin_session, make_engine, make_session_factory, tenant_session
from app.jobs.execute import JobExecutor
from app.jobs.queue import JobQueue
from app.jobs.worker import Worker
from app.main import create_app
from app.services.guard import GuardedWorker
from app.services.webhooks import FakeSender
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_hybrid import frozen_solver
from tests.test_plans_api import TINY

BACKEND = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.now += timedelta(microseconds=1)  # strictly increasing: FIFO order is well defined
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def bare_queue(tmp_path, **kw):
    factory = make_session_factory(make_engine(f"sqlite:///{(tmp_path / 'q.db').as_posix()}", create_tables=True))
    return JobQueue(factory, **kw)


def put(q, kind, n=1):
    ids = []
    with q.factory() as s:
        for _ in range(n):
            ids.append(q.enqueue(s, kind, {"n": len(ids)}))
        s.commit()
    return ids


# ---- claim rules ----------------------------------------------------------------------------
def test_fifo_and_benchmark_jobs_run_alone(tmp_path):
    q = bare_queue(tmp_path, clock=Clock())
    p1 = put(q, "plan")[0]
    b1 = put(q, "benchmark")[0]
    p2 = put(q, "plan")[0]
    assert q.claim("w1").id == p1
    assert q.claim("w2") is None  # the oldest queued job is a benchmark and something is running: wait
    assert q.finish(p1, "w1", "completed")
    assert q.claim("w2").id == b1
    assert q.claim("w3") is None  # nothing starts while a benchmark job runs
    assert q.finish(b1, "w2", "completed")
    assert q.claim("w3").id == p2
    p3 = put(q, "plan")[0]
    assert q.claim("w4").id == p3  # planning jobs may run side by side


def test_concurrent_claims_never_start_two_benchmark_jobs(tmp_path):
    q = bare_queue(tmp_path)
    put(q, "benchmark", n=3)
    got, barrier = [], threading.Barrier(8)

    def claimer(i):
        barrier.wait()
        job = q.claim(f"w{i}")
        if job:
            got.append(job.id)

    threads = [threading.Thread(target=claimer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(got) == 1
    with q.factory() as s:
        assert len(s.scalars(select(Job).where(Job.state == "running")).all()) == 1


def test_stale_job_is_requeued_then_failed_and_old_worker_cannot_finish_it(tmp_path):
    clock = Clock()
    q = bare_queue(tmp_path, stale_s=10, clock=clock)
    jid = put(q, "plan")[0]
    assert q.claim("w1").attempts == 1
    clock.advance(5)
    assert q.heartbeat(jid, "w1") and q.recover_stale() == []  # alive: untouched
    clock.advance(11)
    assert q.recover_stale() == [] and q.get(jid).state == "queued"  # stale: requeued (attempt 1 of 2)
    assert not q.heartbeat(jid, "w1") and not q.finish(jid, "w1", "completed")  # no longer w1's job
    assert q.claim("w2").attempts == 2
    clock.advance(11)
    failed = q.recover_stale()
    assert [j.id for j in failed] == [jid]
    job = q.get(jid)
    assert job.state == "failed" and "stopped during the job 2 time(s)" in job.error
    assert [h["worker_id"] for h in job.history] == ["w1", "w2"]


# ---- through the API --------------------------------------------------------------------------
@pytest.fixture
def ext(tmp_path):
    """API with NO in-process worker (as in production): jobs wait until a worker runs them."""
    app = create_app(tmp_path, worker="external")
    sender = FakeSender()
    app.state.notifier.sender, app.state.notifier.backoff_s = sender, (0.0, 0.0, 0.0)
    c = TestClient(app)
    with admin_session(app.state.db) as s:
        a, b = create_tenant(s, "A"), create_tenant(s, "B")
        _, ka = issue_key(s, a.id)
        _, kb = issue_key(s, b.id)
        s.commit()
    yield {"c": c, "app": app, "sender": sender, "ha": {"X-API-Key": ka}, "hb": {"X-API-Key": kb},
           "a": a.id, "b": b.id, "dir": tmp_path}


def hook(env, h):
    r = env["c"].post("/api/webhooks", headers=h, json={"url": "https://example.org/hook",
                                                        "events": ["plan.completed", "plan.failed"]})
    assert r.status_code == 201, r.text


def make_worker(env, guard=None, **kw):
    app = env["app"]
    return Worker(kw.pop("queue", app.state.queue), JobExecutor(app.state.db, guard, app.state.notifier),
                  worker_id=kw.pop("worker_id", "test-worker"), **kw)


def test_plans_wait_in_the_queue_until_a_worker_runs_them(ext):
    c, app = ext["c"], ext["app"]
    assert app.state.worker is None and c.get("/api/health").json()["jobs"]["worker_mode"] == "external"
    pid = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                 headers=ext["ha"]).json()["plan_id"]
    time.sleep(1.0)
    p = c.get(f"/api/plans/{pid}", headers=ext["ha"]).json()
    assert p["state"] == "queued" and p["job"]["state"] == "queued"  # the API process ran nothing
    assert c.get("/api/health").json()["jobs"]["queued"] == 1
    w = make_worker(ext)
    try:
        assert w.run_once()
    finally:
        w.executor.guard.close()
    p = c.get(f"/api/plans/{pid}", headers=ext["ha"]).json()
    assert p["state"] == "completed" and p["feasible"] is True
    assert p["job"]["state"] == "completed" and p["job"]["attempts"] == 1 and p["job"]["worker_id"] == "test-worker"


def test_hard_timeout_guard_and_webhook_work_through_the_queue(ext):
    hook(ext, ext["ha"])
    pid = ext["c"].post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                        headers=ext["ha"]).json()["plan_id"]
    w = make_worker(ext, guard=GuardedWorker(target=frozen_solver, factor=1.0, grace_s=1.0))
    try:
        w.run_once()
    finally:
        w.executor.guard.close()
    p = ext["c"].get(f"/api/plans/{pid}", headers=ext["ha"]).json()
    assert p["state"] == "completed" and p["status"] == "hard_timeout" and not p["feasible"]
    assert "wall-clock guard" in p["result"]["solve"]["message"]  # stored as what it is, never a success
    ext["app"].state.notifier.drain()
    (call,) = ext["sender"].calls
    body = json.loads(call["body"])
    assert body["event"] == "plan.completed" and body["data"]["status"] == "hard_timeout"


def test_worker_crashing_twice_fails_the_plan_and_says_why(ext):
    hook(ext, ext["ha"])
    clock = Clock()
    q = JobQueue(ext["app"].state.db, stale_s=10, clock=clock)
    pid = ext["c"].post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                        headers=ext["ha"]).json()["plan_id"]
    q.claim("crashing-1")  # claimed, then the worker "dies": no heartbeat, no result
    clock.advance(11)
    w = make_worker(ext, queue=q, worker_id="survivor")
    w.recover()
    assert ext["c"].get(f"/api/plans/{pid}", headers=ext["ha"]).json()["job"]["state"] == "queued"
    q.claim("crashing-2")
    clock.advance(11)
    w.recover()
    p = ext["c"].get(f"/api/plans/{pid}", headers=ext["ha"]).json()
    assert p["state"] == "failed" and "stopped during the job 2 time(s)" in p["error"]
    assert [r["worker_id"] for r in p["job"]["requeues"]] == ["crashing-1", "crashing-2"]
    ext["app"].state.notifier.drain()
    assert [json.loads(c["body"])["event"] for c in ext["sender"].calls] == ["plan.failed"]


def test_a_forged_job_cannot_touch_another_tenants_plan(ext):
    c, app = ext["c"], ext["app"]
    pid_b = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                   headers=ext["hb"]).json()["plan_id"]
    with admin_session(app.state.db) as s:  # B's job, then a job that claims tenant A owns B's plan
        s.query(Job).filter(Job.plan_id == pid_b).update({"state": "completed"})
        forged = app.state.queue.enqueue(s, "plan", {"algorithm": "ortools", "config": {"time_limit_s": 0.5}},
                                         ext["a"], pid_b)
        s.commit()
    w = make_worker(ext)
    w.run_once()
    job = app.state.queue.get(forged)
    assert job.state == "failed" and "not found for tenant" in job.error
    with tenant_session(app.state.db, ext["b"]) as s:
        assert s.get(Plan, pid_b).state == "queued"  # untouched
    assert app.state.queue.for_plan(pid_b, ext["a"]).id == forged  # explicit filter: A sees only A-owned jobs
    assert c.get(f"/api/plans/{pid_b}", headers=ext["ha"]).status_code == 404
    assert c.get(f"/api/plans/{pid_b}", headers=ext["hb"]).json()["job"]["job_id"] != forged


# ---- real worker processes: crash and restart ------------------------------------------------------
def start_worker(db_url, worker_id, log):
    env = {**os.environ, "LOGIMIND_DATABASE_URL": db_url, "LOGIMIND_WORKER_ID": worker_id,
           "LOGIMIND_WORKER_POLL_S": "0.2", "LOGIMIND_WORKER_HEARTBEAT_S": "0.5", "LOGIMIND_JOB_STALE_S": "3"}
    return subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], cwd=BACKEND, env=env,
                            stdout=log, stderr=subprocess.STDOUT)


def wait_for(cond, timeout, what):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what}")


def test_worker_process_crash_and_restart_finishes_the_plan(ext):
    c, app = ext["c"], ext["app"]
    db_url = f"sqlite:///{(ext['dir'] / 'logimind.db').as_posix()}"
    pid = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 2},
                 headers=ext["ha"]).json()["plan_id"]
    job_id = app.state.queue.for_plan(pid, ext["a"]).id
    with open(ext["dir"] / "w1.log", "w") as l1, open(ext["dir"] / "w2.log", "w") as l2:
        w1 = start_worker(db_url, "proc-1", l1)
        try:
            wait_for(lambda: app.state.queue.get(job_id).state == "running", 120, "worker 1 to claim the job")
            w1.kill()  # hard crash in the middle of the job
            w1.wait(timeout=30)
        finally:
            if w1.poll() is None:
                w1.kill()
        assert c.get(f"/api/plans/{pid}", headers=ext["ha"]).json()["state"] in ("queued", "running")
        w2 = start_worker(db_url, "proc-2", l2)
        try:
            wait_for(lambda: c.get(f"/api/plans/{pid}", headers=ext["ha"]).json()["state"] == "completed", 180,
                     "worker 2 to finish the requeued job")
        finally:
            w2.terminate()
            w2.wait(timeout=30)
    p = c.get(f"/api/plans/{pid}", headers=ext["ha"]).json()
    assert p["feasible"] is True and p["job"]["attempts"] == 2 and p["job"]["worker_id"] == "proc-2"
    assert [r["worker_id"] for r in p["job"]["requeues"]] == ["proc-1"]
    with tenant_session(app.state.db, ext["a"]) as s:
        done = s.scalars(select(AuditLog).where(AuditLog.action == "plan.completed")).one()
    assert done.detail["attempt"] == 2 and done.detail["job_id"] == job_id
