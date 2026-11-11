"""The job worker (P6 queue, decision 0021). Run from backend/:

    python -m app.jobs.worker            # uses LOGIMIND_DATABASE_URL, like the API

A worker claims one job at a time, sends a heartbeat every few seconds while it runs, and every
`recover_every_s` requeues jobs whose worker died (see JobQueue.recover_stale). Several workers may run;
benchmark jobs still run alone (queue rules). The API process starts no solver jobs itself unless
LOGIMIND_WORKER=inline (development and tests), which runs this same loop in a thread of the API process.

Environment: LOGIMIND_WORKER_ID (default host-pid), LOGIMIND_WORKER_POLL_S (0.5), LOGIMIND_JOB_STALE_S (30),
LOGIMIND_WORKER_HEARTBEAT_S (2).
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid

from app.jobs.execute import JobError, JobExecutor
from app.jobs.queue import DEFAULT_STALE_S, JobQueue, JobView

log = logging.getLogger("logimind.worker")


def default_worker_id() -> str:
    return os.environ.get("LOGIMIND_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:4]}"


class Worker:
    def __init__(self, queue: JobQueue, executor: JobExecutor, worker_id: str | None = None,
                 poll_s: float = 0.5, heartbeat_s: float = 2.0, recover_every_s: float = 5.0):
        self.queue, self.executor = queue, executor
        self.worker_id = worker_id or default_worker_id()
        self.poll_s, self.heartbeat_s, self.recover_every_s = poll_s, heartbeat_s, recover_every_s
        self.stop = threading.Event()
        self.wake = threading.Event()
        queue.listen(self.wake)
        self._last_recover = 0.0
        self.jobs_done = 0

    def recover(self) -> None:
        for job in self.queue.recover_stale():
            log.warning("job %s failed after repeated worker stops: %s", job.id, job.error)
            self.executor.fail_plan(job, job.error or "worker stopped")

    def run_once(self) -> bool:
        """Recover stale jobs if due, then run at most one job. True if a job ran."""
        if time.monotonic() - self._last_recover >= self.recover_every_s:
            self._last_recover = time.monotonic()
            self.recover()
        job = self.queue.claim(self.worker_id)
        if job is None:
            return False
        self._run(job)
        self.jobs_done += 1
        return True

    def _run(self, job: JobView) -> None:
        done = threading.Event()

        def beat() -> None:
            while not done.wait(self.heartbeat_s):
                if not self.queue.heartbeat(job.id, self.worker_id):
                    log.warning("job %s is no longer ours (requeued after a stale heartbeat)", job.id)
                    return

        hb = threading.Thread(target=beat, name=f"heartbeat-{job.id}", daemon=True)
        hb.start()
        try:
            state, result, error = self.executor.run(job)
        except JobError as exc:
            state, result, error = "failed", None, str(exc)
            self.executor.fail_plan(job, error)
        except Exception as exc:  # reported, never hidden
            state, result, error = "failed", None, f"{type(exc).__name__}: {exc}"
            log.exception("job %s failed", job.id)
            self.executor.fail_plan(job, error)
        finally:
            done.set()
            hb.join(timeout=5)
        if not self.queue.finish(job.id, self.worker_id, state, result, error):
            log.warning("job %s finished here, but it had been requeued; result not recorded on the job", job.id)

    def run_forever(self) -> None:
        log.info("worker %s started", self.worker_id)
        while not self.stop.is_set():
            if not self.run_once():
                self.wake.wait(self.poll_s)
                self.wake.clear()
        log.info("worker %s stopped after %d jobs", self.worker_id, self.jobs_done)

    def start_thread(self) -> "Worker":
        threading.Thread(target=self._run_then_close, name=f"worker-{self.worker_id}", daemon=True).start()
        return self

    def _run_then_close(self) -> None:
        # The thread owns the guarded solver process: after close() it finishes the current job, then stops it.
        # Without this every inline app left one solver process behind (about 500 MB each; the test suite ran out
        # of memory after about 90 of them).
        try:
            self.run_forever()
        finally:
            self.executor.guard.close()

    def close(self) -> None:
        self.stop.set()
        self.wake.set()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw in (None, "") else float(raw)


def worker_from_env(factory, notifier=None, guard=None, queue: JobQueue | None = None) -> Worker:
    queue = queue or JobQueue(factory)
    queue.stale_s = _env_float("LOGIMIND_JOB_STALE_S", DEFAULT_STALE_S)
    return Worker(queue, JobExecutor(factory, guard, notifier), poll_s=_env_float("LOGIMIND_WORKER_POLL_S", 0.5),
                  heartbeat_s=_env_float("LOGIMIND_WORKER_HEARTBEAT_S", 2.0))


def main() -> None:
    from sqlalchemy import inspect

    from app.db.session import database_url, make_engine, make_session_factory
    from app.services.notify import WebhookNotifier
    from app.services.webhooks import HttpxSender

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine = make_engine(database_url())
    while not inspect(engine).has_table("jobs"):  # the API migrates the database on start-up
        log.info("waiting for the database migration (table 'jobs')")
        time.sleep(2)
    factory = make_session_factory(engine)
    notifier = WebhookNotifier(factory, HttpxSender())
    worker = worker_from_env(factory, notifier)
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        worker.close()
    finally:
        notifier.drain()
        worker.executor.guard.close()


if __name__ == "__main__":
    main()
