"""Config file paths, discovery, and TOML read/write."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

CONFIG_FILENAME = "ttd.toml"

# Re-exported for config init / attribution helpers.
__all__ = [
    "CONFIG_FILENAME",
    "find_local_config",
    "global_config_path",
    "load_merged_toml",
    "local_config_write_path",
    "read_toml",
    "update_config_file",
    "write_toml",
]


def global_config_path() -> Path:
    """Return the global config file path (`{XDG_CONFIG_HOME}/ttd/ttd.toml`)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ttd" / CONFIG_FILENAME


def find_local_config(start: Path | None = None) -> Path | None:
    """Walk from *start* (or cwd) toward root; first ``ttd.toml`` wins."""
    current = (start or Path.cwd()).resolve()
    root = current.anchor
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if str(current) == root:
            return None
        current = current.parent


def local_config_write_path() -> Path:
    """Write path: nearest existing local file, else cwd ``ttd.toml``."""
    existing = find_local_config()
    if existing is not None:
        return existing
    return Path.cwd() / CONFIG_FILENAME


def read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file; return an empty dict when *path* is missing."""
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    if not isinstance(data, dict):
        return {}
    return data


def write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write *data* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        tomli_w.dump(data, fh)


def load_merged_toml() -> tuple[dict[str, Any], dict[str, Any], Path, Path | None]:
    """Load global and local TOML layers plus their resolved paths."""
    global_path = global_config_path()
    local_path = find_local_config()
    global_data = read_toml(global_path)
    local_data = read_toml(local_path) if local_path is not None else {}
    return global_data, local_data, global_path, local_path


def update_config_file(path: Path, key: str, value: object) -> None:
    """Update a single top-level key in *path*, preserving other keys."""
    data = read_toml(path)
    data[key] = value
    write_toml(path, data)
