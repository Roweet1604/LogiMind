"""Apply Alembic migrations programmatically (app start-up and tests use the same path as the CLI)."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[2]


def upgrade_to_head(url: str) -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
