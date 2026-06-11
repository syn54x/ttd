"""Style-preserving config writes for `ttd config set/unset` (tomlkit)."""

from pathlib import Path

import tomlkit
from pydantic import ValidationError

from ttd.config.loader import LOCAL_CONFIG_NAME, global_config_path
from ttd.config.schema import Settings
from ttd.core.errors import ConfigError


def target_path(local: bool, start: Path | None = None) -> Path:
    if local:
        return (start or Path.cwd()) / LOCAL_CONFIG_NAME
    return global_config_path()


def _coerce(raw: str) -> object:
    """Parse a CLI string the way TOML would: bool, int, float, else string."""
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _validate_key(dotted: str, value: object | None) -> None:
    parts = dotted.split(".")
    if len(parts) != 2:
        raise ConfigError(f"Config keys are 'section.key' (got '{dotted}')")
    section, key = parts
    probe: dict = {section: {key: value}} if value is not None else {}
    try:
        Settings.model_validate(probe)
    except ValidationError as exc:
        first = exc.errors()[0]
        if first["type"] == "extra_forbidden":
            raise ConfigError(f"Unknown config key '{dotted}'") from exc
        raise ConfigError(f"Invalid value for '{dotted}': {first['msg']}") from exc


def set_value(dotted: str, raw: str, local: bool, start: Path | None = None) -> Path:
    value = _coerce(raw)
    _validate_key(dotted, value)
    path = target_path(local, start)
    doc = tomlkit.parse(path.read_text()) if path.is_file() else tomlkit.document()
    section, key = dotted.split(".")
    if section not in doc:
        doc[section] = tomlkit.table()
    doc[section][key] = value  # type: ignore[index]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc))
    return path


def unset_value(dotted: str, local: bool, start: Path | None = None) -> Path:
    _validate_key(dotted, None)
    path = target_path(local, start)
    if not path.is_file():
        raise ConfigError(f"No config file at {path}")
    doc = tomlkit.parse(path.read_text())
    section, key = dotted.split(".")
    try:
        del doc[section][key]  # type: ignore[union-attr]
        if not doc[section]:
            del doc[section]
    except KeyError as exc:
        raise ConfigError(f"'{dotted}' is not set in {path}") from exc
    path.write_text(tomlkit.dumps(doc))
    return path
