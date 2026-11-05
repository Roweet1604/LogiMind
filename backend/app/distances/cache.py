"""Persistent matrix cache (SQLite file, standard library only).

Key = SHA-256 of (provider, server URL, profile, points). The value is the whole matrix with its
provenance. Entries older than `max_age_days` are ignored and replaced, so a server whose map data
was updated is asked again eventually. Only real provider answers are cached, never a fallback.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from app.distances.base import Point, RoadMatrix

DEFAULT_MAX_AGE_DAYS = 30.0


def cache_key(provider_id: str, points: list[Point]) -> str:
    return hashlib.sha256(json.dumps([provider_id, [list(p) for p in points]]).encode()).hexdigest()


class MatrixCache:
    def __init__(self, path: Path, max_age_days: float = DEFAULT_MAX_AGE_DAYS):
        self.path = Path(path)
        self.max_age = timedelta(days=max_age_days)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS matrix_cache (key TEXT PRIMARY KEY, provider TEXT NOT NULL, "
                      "n INTEGER NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            with conn:  # commit or roll back
                yield conn
        finally:
            conn.close()  # Windows keeps the file locked otherwise

    def get(self, key: str) -> RoadMatrix | None:
        with self._connect() as c:
            row = c.execute("SELECT created_at, payload FROM matrix_cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        if datetime.now(timezone.utc) - datetime.fromisoformat(row[0]) > self.max_age:
            return None
        return RoadMatrix.from_dict(json.loads(row[1]))

    def put(self, key: str, m: RoadMatrix) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as c:
            c.execute("INSERT OR REPLACE INTO matrix_cache VALUES (?, ?, ?, ?, ?)",
                      (key, m.provider, len(m.points), now, json.dumps(m.to_dict())))

    def __len__(self) -> int:
        with self._connect() as c:
            return c.execute("SELECT COUNT(*) FROM matrix_cache").fetchone()[0]
