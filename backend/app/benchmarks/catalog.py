"""Benchmark catalogue: where downloaded instances live, the best-known
solutions (BKS) table with provenance, and the gap to a BKS.

Instance files are NOT stored in git (CVRPLIB provides them for research use;
redistribution may carry extra terms). `experiments/benchmarks/fetch_benchmarks.py`
downloads them into `experiments/benchmarks/data/` (git-ignored). Only the BKS
table (`experiments/benchmarks/bks.csv`: values, source URL, retrieval date) is
committed.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.benchmarks.formats import parse_solomon, parse_solution, parse_tsplib_cvrp
from app.models.problem import Instance

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH_DIR = Path(os.environ.get("LOGIMIND_BENCHMARK_DIR", REPO_ROOT / "experiments" / "benchmarks"))


@dataclass(frozen=True)
class SetInfo:
    key: str               # folder name under data/ and the "set" column of bks.csv
    problem: str           # "CVRP" or "VRPTW"
    file_format: str       # "solomon" or "tsplib"
    routes_rule: str       # how CVRPLIB scores the number of routes
    distance_convention: str


SETS: dict[str, SetInfo] = {
    "solomon": SetInfo("solomon", "VRPTW", "solomon", "at_most_vehicles",
                       "Euclidean truncated to one decimal; objective total distance"),
    "homberger": SetInfo("homberger", "VRPTW", "solomon", "at_most_vehicles",
                         "Euclidean truncated to one decimal; objective total distance"),
    "A": SetInfo("A", "CVRP", "tsplib", "fixed", "Euclidean rounded to nearest integer (TSPLIB)"),
    "B": SetInfo("B", "CVRP", "tsplib", "fixed", "Euclidean rounded to nearest integer (TSPLIB)"),
    "P": SetInfo("P", "CVRP", "tsplib", "fixed", "Euclidean rounded to nearest integer (TSPLIB)"),
    "X": SetInfo("X", "CVRP", "tsplib", "free", "Euclidean rounded to nearest integer (TSPLIB)"),
}
EXTENSIONS = {"solomon": ".txt", "tsplib": ".vrp"}


@dataclass(frozen=True)
class BKS:
    instance: str
    set: str
    problem: str
    n_customers: int
    cost: float
    routes: int
    distance_convention: str
    routes_rule: str
    source_url: str
    retrieved_on: str


def bks_path() -> Path:
    return BENCH_DIR / "bks.csv"


def load_bks(path: Path | None = None) -> dict[str, BKS]:
    path = path or bks_path()
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {r["instance"]: BKS(r["instance"], r["set"], r["problem"], int(r["n_customers"]),
                                   float(r["bks_cost"]), int(r["bks_routes"]), r["distance_convention"],
                                   r["routes_rule"], r["source_url"], r["retrieved_on"])
                for r in csv.DictReader(f)}


def re_safe_name(name: str) -> bool:
    """Benchmark names are short tokens like C101, A-n32-k5 or C1_2_1 (no paths)."""
    return re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name) is not None


def data_file(set_key: str, name: str, solution: bool = False) -> Path:
    info = SETS[set_key]
    ext = ".sol" if solution else EXTENSIONS[info.file_format]
    return BENCH_DIR / "data" / set_key / f"{name}{ext}"


def load_instance(set_key: str, name: str) -> Instance:
    """Parse a downloaded benchmark file into an Instance.

    Route rules: "fixed" sets (A/B/P) get the k from the name as the fleet size;
    "free" sets (X) get one vehicle per customer, i.e. no fleet limit;
    VRPTW sets use the vehicle number in the file as the limit."""
    if set_key not in SETS:
        raise KeyError(f"unknown benchmark set {set_key!r}; known: {sorted(SETS)}")
    info = SETS[set_key]
    path = data_file(set_key, name)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download it first: python experiments/benchmarks/fetch_benchmarks.py")
    text = path.read_text(encoding="utf-8", errors="replace")
    source = f"benchmark:{set_key}:{name}"
    if info.file_format == "solomon":
        return parse_solomon(text, name=name, source=source)
    inst = parse_tsplib_cvrp(text, source=source)
    if info.routes_rule == "free":
        inst = parse_tsplib_cvrp(text, vehicle_count=len(inst.customers), source=source)
    return inst


def load_solution(set_key: str, name: str) -> tuple[list[list[int]], float]:
    path = data_file(set_key, name, solution=True)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    return parse_solution(path.read_text(encoding="utf-8", errors="replace"))


def available(set_key: str) -> list[str]:
    folder = BENCH_DIR / "data" / set_key
    ext = EXTENSIONS[SETS[set_key].file_format]
    return sorted(p.stem for p in folder.glob(f"*{ext}")) if folder.exists() else []


def gap_pct(cost: float, bks_cost: float) -> float:
    """Relative gap to a best-known cost, in percent (positive = worse than BKS)."""
    if bks_cost <= 0:
        raise ValueError("best-known cost must be positive")
    return 100.0 * (cost - bks_cost) / bks_cost
