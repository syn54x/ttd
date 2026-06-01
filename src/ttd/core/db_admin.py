"""Database location and maintenance (local SQLite / ferro-orm)."""

from __future__ import annotations

import shutil
import sqlite3
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


class BackupResult(BaseModel):
    """Outcome of copying the ledger database to a backup path."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    destination: Path
    """Backup file path written by ``backup_database``."""

    size_bytes: int
    """Size of the backup file in bytes."""


def _sidecar_paths(db_path: Path) -> tuple[Path, Path]:
    return db_path.with_name(f"{db_path.name}-wal"), db_path.with_name(
        f"{db_path.name}-shm"
    )


def _remove_db_files(db_path: Path) -> None:
    wal_path, shm_path = _sidecar_paths(db_path)
    for path in (db_path, wal_path, shm_path):
        if path.exists():
            path.unlink()


def _validate_sqlite_file(path: Path) -> None:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ValidationError(f"{path} is not a readable SQLite database") from exc
    try:
        connection.execute("SELECT 1")
    except sqlite3.Error as exc:
        raise ValidationError(f"{path} is not a readable SQLite database") from exc
    finally:
        connection.close()


def _sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    source_conn = sqlite3.connect(source)
    dest_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()


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
    _remove_db_files(path)
    await init_db(cfg)
    return describe_db(cfg)


async def backup_database(
    destination: Path,
    settings: Settings | None = None,
) -> BackupResult:
    """Copy the active ledger database to ``destination`` via SQLite backup."""
    cfg = settings or config.get_settings()
    location = describe_db(cfg)
    if not location.exists:
        raise ValidationError(
            f"No ledger database at {location.db_path}. Run `ttd db migrate` first."
        )
    await close_db()
    _sqlite_backup(location.db_path, destination)
    size = destination.stat().st_size
    await init_db(cfg)
    return BackupResult(destination=destination, size_bytes=size)


async def restore_database(
    source: Path,
    settings: Settings | None = None,
    *,
    confirmed: bool = False,
) -> DbLocation:
    """Replace the active ledger database with a backup file."""
    if not confirmed:
        raise ValidationError(
            "Database restore is destructive. Re-run with --yes to confirm."
        )
    if not source.is_file():
        raise ValidationError(f"Backup file not found: {source}")
    _validate_sqlite_file(source)

    cfg = settings or config.get_settings()
    await close_db()
    db_path = cfg.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _remove_db_files(db_path)
    shutil.copy2(source, db_path)
    await init_db(cfg)
    return describe_db(cfg)
