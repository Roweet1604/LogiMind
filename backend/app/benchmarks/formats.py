"""Parsers for public benchmark files (as distributed by CVRPLIB).

* Solomon / Gehring-Homberger VRPTW text files -> CVRPTW `Instance`
  (metric "euclidean_trunc1": CVRPLIB's convention for these sets; travel
  time = distance; objective = total distance, so fixed vehicle cost is 0).
* TSPLIB CVRP files (EUC_2D) -> CVRP `Instance` (metric "euclidean_nint").
* CVRPLIB ".sol" files -> (routes, cost). Customers in .sol files are numbered
  1..n in file order with the depot removed; the parsers use the same numbering,
  so solution routes can be validated directly against the parsed instance.
"""
from __future__ import annotations

import re

from app.models.problem import Customer, Instance


class BenchmarkFormatError(ValueError):
    pass


def parse_solomon(text: str, name: str | None = None, source: str = "benchmark:solomon") -> Instance:
    lines = [ln.strip() for ln in text.splitlines()]
    nonempty = [ln for ln in lines if ln]
    if not nonempty:
        raise BenchmarkFormatError("empty Solomon file")
    file_name = nonempty[0]
    try:
        v_idx = next(i for i, ln in enumerate(nonempty) if ln.upper().startswith("VEHICLE"))
        vehicles, capacity = (int(v) for v in nonempty[v_idx + 2].split()[:2])
        c_idx = next(i for i, ln in enumerate(nonempty) if ln.upper().startswith("CUSTOMER"))
    except (StopIteration, ValueError, IndexError) as exc:
        raise BenchmarkFormatError(f"not a Solomon-format file: {exc!r}") from exc

    rows: list[list[float]] = []
    for ln in nonempty[c_idx + 1:]:
        parts = ln.split()
        if len(parts) != 7 or not re.fullmatch(r"\d+", parts[0]):
            continue  # header line(s)
        rows.append([float(p) for p in parts])
    if len(rows) < 2 or int(rows[0][0]) != 0:
        raise BenchmarkFormatError("Solomon file needs a depot row (id 0) followed by customers")

    depot, custs = rows[0], rows[1:]
    customers = [Customer(int(r[0]), r[1], r[2], int(r[3]), ready_time=r[4], due_time=r[5], service_time=r[6])
                 for r in custs]
    return Instance(
        depot_x=depot[1], depot_y=depot[2], customers=customers,
        vehicle_count=vehicles, vehicle_capacity=capacity,
        metric="euclidean_trunc1", distance_unit="unit",
        fixed_vehicle_cost=0.0, cost_per_distance=1.0,
        name=name or file_name, source=source,
        depot_ready_time=depot[4], depot_due_time=depot[5],
        time_per_distance=1.0, time_unit="unit",
    )


def parse_tsplib_cvrp(text: str, vehicle_count: int | None = None,
                      source: str = "benchmark:cvrplib") -> Instance:
    header: dict[str, str] = {}
    coords: dict[int, tuple[float, float]] = {}
    demands: dict[int, int] = {}
    depots: list[int] = []
    section = None
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        up = ln.upper()
        if up.startswith("EOF"):
            break
        if up.endswith("_SECTION"):
            section = up
            continue
        if section is None:
            if ":" in ln:
                k, v = ln.split(":", 1)
                header[k.strip().upper()] = v.strip()
            continue
        parts = ln.split()
        if section == "NODE_COORD_SECTION":
            coords[int(parts[0])] = (float(parts[1]), float(parts[2]))
        elif section == "DEMAND_SECTION":
            demands[int(parts[0])] = int(parts[1])
        elif section == "DEPOT_SECTION":
            if int(parts[0]) >= 0:
                depots.append(int(parts[0]))
        else:
            raise BenchmarkFormatError(f"unsupported section {section}")

    if header.get("EDGE_WEIGHT_TYPE", "").upper() != "EUC_2D":
        raise BenchmarkFormatError(f"only EUC_2D is supported, got {header.get('EDGE_WEIGHT_TYPE')!r}")
    if len(depots) != 1:
        raise BenchmarkFormatError(f"expected exactly one depot, got {depots}")
    try:
        name = header["NAME"]
        dimension = int(header["DIMENSION"])
        capacity = int(header["CAPACITY"])
    except (KeyError, ValueError) as exc:
        raise BenchmarkFormatError(f"missing or bad header field: {exc!r}") from exc
    if len(coords) != dimension or set(coords) != set(demands):
        raise BenchmarkFormatError("coordinates and demands do not match DIMENSION")

    depot = depots[0]
    others = [k for k in sorted(coords) if k != depot]
    customers = [Customer(i, coords[k][0], coords[k][1], demands[k]) for i, k in enumerate(others, start=1)]
    if vehicle_count is None:
        m = re.search(r"-k(\d+)", name)
        if not m:
            raise BenchmarkFormatError(f"cannot infer the vehicle count from name {name!r}; pass vehicle_count")
        vehicle_count = int(m.group(1))
    return Instance(
        depot_x=coords[depot][0], depot_y=coords[depot][1], customers=customers,
        vehicle_count=vehicle_count, vehicle_capacity=capacity,
        metric="euclidean_nint", distance_unit="unit",
        fixed_vehicle_cost=0.0, cost_per_distance=1.0, name=name, source=source,
    )


def parse_solution(text: str) -> tuple[list[list[int]], float]:
    routes: list[list[int]] = []
    cost = None
    for ln in text.splitlines():
        ln = ln.strip()
        m = re.match(r"Route\s*#\s*\d+\s*:(.*)$", ln, re.I)
        if m:
            routes.append([int(x) for x in m.group(1).split()])
        elif ln.lower().startswith("cost"):
            cost = float(ln.split()[1])
    if cost is None or not routes:
        raise BenchmarkFormatError("solution file needs 'Route #k:' lines and a 'Cost' line")
    return routes, cost
