"""Common result schema returned by every solver."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

# Solver-level status (NOT a feasibility claim; the validator decides that).
SOLVED = "solved"                      # solver returned a candidate solution
NO_SOLUTION = "no_solution"            # solver ran but found nothing / proved infeasible
TIMEOUT_NO_SOLUTION = "timeout_no_solution"  # time limit hit before any solution
INVALID_INPUT = "invalid_input"
ERROR = "error"


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


@dataclass
class SolveResult:
    instance_id: str
    algorithm: str                      # "ortools" | "ga"
    status: str
    runtime_seconds: float              # wall clock: model build + search; excludes distance-matrix build
    routes: list[list[int]] | None      # customer IDs per vehicle, depot implicit at both ends
    config: dict[str, Any]
    seed: int | None = None
    message: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=new_run_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "instance_id": self.instance_id, "algorithm": self.algorithm,
            "status": self.status, "runtime_seconds": self.runtime_seconds, "routes": self.routes,
            "config": self.config, "seed": self.seed, "message": self.message,
            "diagnostics": self.diagnostics,
        }
