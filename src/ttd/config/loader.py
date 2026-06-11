"""Layered config loading.

Precedence (high → low): TTD_* env vars → nearest .ttd.toml (walking up from
cwd) → global config.toml → built-in defaults. CLI flags override above this
layer, at the command level. Provenance records which layer set each key.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ttd.config.schema import Settings
from ttd.core.errors import ConfigError

LOCAL_CONFIG_NAME = ".ttd.toml"

Provenance = dict[str, str]  # "section.key" -> default|global|local|env


def global_config_path(env: dict[str, str] | None = None) -> Path:
    env = env if env is not None else dict(os.environ)
    if ttd_dir := env.get("TTD_CONFIG_DIR"):
        return Path(ttd_dir).expanduser() / "config.toml"
    if xdg := env.get("XDG_CONFIG_HOME"):
        return Path(xdg).expanduser() / "ttd" / "config.toml"
    return Path.home() / ".config" / "ttd" / "config.toml"


def find_local_config(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default cwd) to the nearest .ttd.toml.

    Stops at $HOME when start is inside it (a config in ~ itself still counts),
    otherwise walks to the filesystem root.
    """
    current = (start or Path.cwd()).resolve()
    home = Path.home().resolve()
    for candidate_dir in [current, *current.parents]:
        candidate = candidate_dir / LOCAL_CONFIG_NAME
        if candidate.is_file():
            return candidate
        if candidate_dir == home:
            break
    return None


def _read_toml(path: Path, layer: str) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {layer} config {path}: {exc}") from exc


def _merge(
    base: dict, override: dict, layer: str, provenance: Provenance, prefix: str = ""
) -> dict:
    out = dict(base)
    for key, value in override.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value, layer, provenance, f"{dotted}.")
        elif isinstance(value, dict):
            out[key] = _merge({}, value, layer, provenance, f"{dotted}.")
        else:
            out[key] = value
            provenance[dotted] = layer
    return out


def _env_overrides(env: dict[str, str]) -> dict:
    """TTD_<SECTION>__<KEY>=value → {section: {key: value}}. TTD_DB_PATH is a shortcut."""
    data: dict = {}
    for name, raw in env.items():
        if name == "TTD_DB_PATH":
            data.setdefault("storage", {})["db_path"] = raw
            continue
        if not name.startswith("TTD_") or "__" not in name:
            continue
        section, _, key = name.removeprefix("TTD_").partition("__")
        if not section or not key:
            continue
        value: object = raw
        if raw.lower() in ("true", "false"):
            value = raw.lower() == "true"
        data.setdefault(section.lower(), {})[key.lower()] = value
    return data


@dataclass
class LoadedConfig:
    settings: Settings
    provenance: Provenance
    global_path: Path
    local_path: Path | None = None
    field_order: list[str] = field(default_factory=list)


def load_config(
    start: Path | None = None,
    env: dict[str, str] | None = None,
) -> LoadedConfig:
    env = env if env is not None else dict(os.environ)
    provenance: Provenance = {}

    data: dict = {}
    gpath = global_config_path(env)
    if gpath.is_file():
        data = _merge(data, _read_toml(gpath, "global"), "global", provenance)

    lpath = find_local_config(start)
    if lpath is not None:
        data = _merge(data, _read_toml(lpath, "local"), "local", provenance)

    data = _merge(data, _env_overrides(env), "env", provenance)

    try:
        settings = Settings.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise ConfigError(f"Invalid config value for '{loc}': {first['msg']}") from exc
    return LoadedConfig(
        settings=settings, provenance=provenance, global_path=gpath, local_path=lpath
    )


def get_settings() -> Settings:
    """Load effective settings fresh. TOML files are tiny; no caching needed,
    and fresh loads keep in-process callers (tests, TUI) coherent after writes."""
    return load_config().settings
