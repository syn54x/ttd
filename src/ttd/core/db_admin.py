"""Database location and maintenance (local SQLite / ferro-orm)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ttd.core import config
from ttd.core.config import Settings
from ttd.core.db import close_db, init_db
from ttd.core.exceptions import ValidationError


class DbLocation(BaseModel):
    """Resolved database paths for a settings profile."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    data_dir: Path
    """Ledger data directory (TTD_DATA_DIR)."""

    db_path: Path
    """SQLite database file path."""

    db_dsn: str
    """ferro-orm connection DSN."""

    exists: bool
    """Whether the database file is present on disk."""

    size_bytes: int | None
    """File size when ``exists`` is true."""


def describe_db(settings: Settings | None = None) -> DbLocation:
    """Return database paths and file metadata without opening a connection."""
    cfg = settings or config.get_settings()
    path = cfg.db_path
    size: int | None = None
    if path.exists():
        size = path.stat().st_size
    return DbLocation(
        data_dir=cfg.data_dir,
        db_path=path,
        db_dsn=cfg.db_dsn,
        exists=path.exists(),
        size_bytes=size,
    )


async def apply_schema(settings: Settings | None = None) -> DbLocation:
    """Connect and apply model schema via ferro ``auto_migrate``."""
    cfg = settings or config.get_settings()
    await close_db()
    await init_db(cfg)
    return describe_db(cfg)


async def reset_database(
    settings: Settings | None = None, *, confirmed: bool = False
) -> DbLocation:
    """Delete the database file and recreate an empty schema.

    Requires ``confirmed=True`` so callers (CLI) must pass an explicit flag.
    """
    if not confirmed:
        raise ValidationError(
            "Database reset is destructive. Re-run with --yes to confirm."
        )
    cfg = settings or config.get_settings()
    await close_db()
    path = cfg.db_path
    if path.exists():
        path.unlink()
    await init_db(cfg)
    return describe_db(cfg)
