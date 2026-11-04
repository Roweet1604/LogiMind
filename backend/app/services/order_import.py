"""CSV / Excel order import with a row-level validation report (P6c).

Required columns: id, demand, and either x + y or lon + lat (lon -> x, lat -> y,
for haversine instances). Optional: ready_time, due_time, service_time.
Header names are case-insensitive; surrounding spaces are ignored.
Every row is checked; the report lists each bad row with its spreadsheet row number
(header = row 1) and every problem found, so the user can fix the file in one pass.
Nothing is imported unless every row is valid.
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from typing import Any

MAX_ROWS = 1000  # same cap as POST /api/instances
OPTIONAL = ("ready_time", "due_time", "service_time")
ALIASES = {"lon": "x", "lng": "x", "longitude": "x", "lat": "y", "latitude": "y", "customer_id": "id"}


class ImportFileError(ValueError):
    """The file as a whole cannot be read (wrong type, no header, missing columns, too many rows)."""


@dataclass
class RowIssue:
    row: int
    field: str
    message: str


@dataclass
class ImportReport:
    rows: int = 0
    valid_rows: int = 0
    issues: list[RowIssue] = field(default_factory=list)
    customers: list[dict[str, Any]] = field(default_factory=list)
    coordinates: str = "xy"  # or "lonlat"

    @property
    def ok(self) -> bool:
        return self.rows > 0 and not self.issues

    def to_dict(self) -> dict[str, Any]:
        bad_rows = sorted({i.row for i in self.issues})
        return {"ok": self.ok, "rows": self.rows, "valid_rows": self.valid_rows, "invalid_rows": len(bad_rows),
                "coordinates": self.coordinates,
                "issues": [i.__dict__ for i in self.issues],
                "customers": self.customers if self.ok else []}


def _read_table(filename: str, data: bytes) -> list[list[Any]]:
    name = filename.lower()
    if name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ImportFileError("CSV must be UTF-8 encoded")
        return [r for r in csv.reader(io.StringIO(text))]
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # corrupt or not really xlsx
            raise ImportFileError(f"cannot read Excel file: {type(exc).__name__}")
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    raise ImportFileError("file must be .csv or .xlsx")


def _num(v: Any) -> float | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        raise ValueError
    f = float(str(v).strip()) if isinstance(v, str) else float(v)
    if not math.isfinite(f):
        raise ValueError
    return f


def parse_orders(filename: str, data: bytes) -> ImportReport:
    table = [r for r in _read_table(filename, data)]
    while table and all(c is None or str(c).strip() == "" for c in table[-1]):
        table.pop()
    if not table:
        raise ImportFileError("file is empty")
    header = [ALIASES.get(str(h or "").strip().lower(), str(h or "").strip().lower()) for h in table[0]]
    raw_header = {str(h or "").strip().lower() for h in table[0]}
    missing = [c for c in ("id", "x", "y", "demand") if c not in header]
    if missing:
        raise ImportFileError(f"missing required column(s): {', '.join(missing)} "
                              "(need id, demand and x/y or lon/lat)")
    dupes = sorted({h for h in header if h and header.count(h) > 1})
    if dupes:
        raise ImportFileError(f"duplicate column(s): {', '.join(dupes)}")
    body = table[1:]
    if len(body) > MAX_ROWS:
        raise ImportFileError(f"too many rows ({len(body)}); the limit is {MAX_ROWS}")
    rep = ImportReport(coordinates="lonlat" if raw_header & {"lon", "lng", "longitude"} else "xy")
    col = {h: i for i, h in enumerate(header) if h}
    seen: dict[int, int] = {}
    for offset, raw in enumerate(body):
        row_no = offset + 2
        if all(c is None or str(c).strip() == "" for c in raw):
            continue  # blank line inside the file
        rep.rows += 1
        issues: list[RowIssue] = []
        vals: dict[str, Any] = {}

        def get(name: str) -> Any:
            i = col.get(name)
            return raw[i] if i is not None and i < len(raw) else None

        for name in ("id", "x", "y", "demand", *OPTIONAL):
            if name not in col and name in OPTIONAL:
                continue
            try:
                vals[name] = _num(get(name))
            except (TypeError, ValueError):
                issues.append(RowIssue(row_no, name, f"not a number: {get(name)!r}"))
                continue
            if vals[name] is None and name not in OPTIONAL:
                issues.append(RowIssue(row_no, name, "required value is empty"))
        if vals.get("id") is not None:
            if not float(vals["id"]).is_integer() or vals["id"] < 1:
                issues.append(RowIssue(row_no, "id", "must be a whole number >= 1"))
            elif int(vals["id"]) in seen:
                issues.append(RowIssue(row_no, "id", f"duplicate id {int(vals['id'])} (first on row "
                                                     f"{seen[int(vals['id'])]})"))
            else:
                seen[int(vals["id"])] = row_no
        if vals.get("demand") is not None and (not float(vals["demand"]).is_integer() or vals["demand"] <= 0):
            issues.append(RowIssue(row_no, "demand", "must be a whole number > 0"))
        if rep.coordinates == "lonlat":
            if vals.get("x") is not None and not -180 <= vals["x"] <= 180:
                issues.append(RowIssue(row_no, "lon", "longitude must be between -180 and 180"))
            if vals.get("y") is not None and not -90 <= vals["y"] <= 90:
                issues.append(RowIssue(row_no, "lat", "latitude must be between -90 and 90"))
        for name in OPTIONAL:
            if vals.get(name) is not None and vals[name] < 0:
                issues.append(RowIssue(row_no, name, "must be >= 0"))
        ready, due = vals.get("ready_time"), vals.get("due_time")
        if ready is not None and due is not None and due < ready:
            issues.append(RowIssue(row_no, "due_time", f"due_time {due:g} is before ready_time {ready:g}"))
        if issues:
            rep.issues.extend(issues)
            continue
        rep.valid_rows += 1
        cust: dict[str, Any] = {"id": int(vals["id"]), "x": vals["x"], "y": vals["y"], "demand": int(vals["demand"])}
        for name in OPTIONAL:
            if vals.get(name) is not None:
                cust[name] = vals[name]
        rep.customers.append(cust)
    if rep.rows == 0:
        raise ImportFileError("file has a header but no data rows")
    return rep
