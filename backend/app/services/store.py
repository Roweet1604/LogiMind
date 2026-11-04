"""In-process store + JSON-file persistence + single-worker execution.

One worker thread runs solver jobs strictly one at a time, each inside the
guarded worker process (services/guard.py: a run that overruns its time limit
is killed and reported as hard_timeout). This is deliberate:
runs are compared by wall-clock time, so concurrent jobs would compete for CPU
and make the comparison unfair.

Files under data_dir: instances/<id>.json, runs/<id>.json, experiments/<id>.json
(completed runs and experiments only; queued runs do not survive a restart).
"""
from __future__ import annotations

import json
import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.models.problem import Instance
from app.services.export import summarize
from app.services.guard import GuardedWorker
from app.services.runner import RunRecord

TERMINAL = {"completed", "failed"}


def _clean(obj: Any) -> Any:
    """Make a structure strictly JSON-safe: NaN/inf -> None."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalar
        return _clean(obj.item())
    return obj


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        for sub in ("instances", "runs", "experiments"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="solver")
        self.guard = GuardedWorker()
        self.instances: dict[str, Instance] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.experiments: dict[str, dict[str, Any]] = {}
        self._load()

    # ---- persistence ----------------------------------------------------
    def _write(self, kind: str, key: str, data: dict) -> None:
        (self.dir / kind / f"{key}.json").write_text(json.dumps(_clean(data), indent=1))

    def _load(self) -> None:
        for p in sorted((self.dir / "instances").glob("*.json")):
            inst = Instance.from_dict(json.loads(p.read_text()))
            self.instances[inst.instance_id] = inst
        for p in sorted((self.dir / "runs").glob("*.json")):
            d = json.loads(p.read_text())
            self.runs[d["run_id"]] = d
        for p in sorted((self.dir / "experiments").glob("*.json")):
            d = json.loads(p.read_text())
            self.experiments[d["experiment_id"]] = d

    # ---- instances ------------------------------------------------------
    def add_instance(self, inst: Instance) -> Instance:
        with self.lock:
            self.instances[inst.instance_id] = inst
            self._write("instances", inst.instance_id, inst.to_dict())
        return inst

    # ---- runs -----------------------------------------------------------
    def submit_run(self, instance_id: str, algorithm: str, config: dict[str, Any],
                   experiment_id: str | None = None, meta: dict[str, Any] | None = None) -> str:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        inst = self.instances[instance_id]
        with self.lock:
            self.runs[run_id] = {
                "run_id": run_id, "instance_id": instance_id, "instance_name": inst.name,
                "n_customers": len(inst.customers), "algorithm": algorithm, "state": "queued",
                "experiment_id": experiment_id, "created_at": _now(), "requested_config": config,
                "error": None, "result": None, "validation": None, "metrics": None, "row": None,
                **_clean(meta or {}),
            }
        self.executor.submit(self._execute, run_id, config)
        return run_id

    def _execute(self, run_id: str, config: dict[str, Any]) -> None:
        with self.lock:
            self.runs[run_id] = {**self.runs[run_id], "state": "running"}
            base = self.runs[run_id]
        try:
            rec: RunRecord = self.guard.run(self.instances[base["instance_id"]], base["algorithm"], config)
            rec.result.run_id = run_id
            update = {
                "state": "completed", "started_at": rec.started_at, "result": rec.result.to_dict(),
                "validation": rec.validation.to_dict() if rec.validation else None,
                "metrics": rec.metrics.to_dict() if rec.metrics else None,
                "row": rec.to_row(),
            }
        except Exception as exc:  # reported, never hidden
            update = {"state": "failed", "error": f"{type(exc).__name__}: {exc}"}
        with self.lock:
            final = _clean({**self.runs[run_id], **update})
            if final.get("row"):
                final["row"]["run_id"] = run_id
            self.runs[run_id] = final
            self._write("runs", run_id, final)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.lock:
            return self.runs.get(run_id)

    def list_runs(self, instance_id: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            runs = list(self.runs.values())
        if instance_id:
            runs = [r for r in runs if r["instance_id"] == instance_id]
        return sorted(runs, key=lambda r: r["created_at"], reverse=True)

    # ---- experiments ----------------------------------------------------
    def submit_experiment(self, instance_id: str, params: dict[str, Any], jobs: list[tuple[str, dict]]) -> str:
        exp_id = f"exp-{uuid.uuid4().hex[:10]}"
        run_ids = [self.submit_run(instance_id, algo, cfg, exp_id) for algo, cfg in jobs]
        exp = {"experiment_id": exp_id, "instance_id": instance_id, "created_at": _now(),
               "params": params, "run_ids": run_ids}
        with self.lock:
            self.experiments[exp_id] = exp
            self._write("experiments", exp_id, exp)
        return exp_id

    def experiment_view(self, exp_id: str) -> dict[str, Any] | None:
        with self.lock:
            exp = self.experiments.get(exp_id)
            if exp is None:
                return None
            runs = [self.runs.get(rid) for rid in exp["run_ids"]]
        present = [r for r in runs if r]
        lost = len(runs) - len(present)
        if any(r["state"] not in TERMINAL for r in present):
            state = "running"
        elif lost:
            state = "incomplete"  # runs lost to a server restart
        elif any(r["state"] == "failed" for r in present):
            state = "completed_with_failures"
        else:
            state = "completed"
        rows = [r["row"] for r in present if r.get("row")]
        summary = []
        if rows:
            df = pd.DataFrame(rows)
            summary = json.loads(summarize(df).to_json(orient="records"))
        return {**exp, "state": state, "lost_runs": lost,
                "runs": [{k: r.get(k) for k in ("run_id", "algorithm", "state", "row", "error")} for r in present],
                "summary": summary}

    def experiment_rows(self, exp_id: str) -> list[dict[str, Any]] | None:
        view = self.experiment_view(exp_id)
        if view is None:
            return None
        return [r["row"] for r in view["runs"] if r.get("row")]
