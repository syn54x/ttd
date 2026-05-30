from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import TomlConfigSettingsSource

from ttd.core.config_files import (
    find_local_config,
    global_config_path,
    load_merged_toml,
    local_config_write_path,
    read_toml,
    update_config_file,
    write_toml,
)
from ttd.core.exceptions import ValidationError

SettingSource = Literal["env", "local", "global", "default"]

CONFIG_KEYS: tuple[str, ...] = (
    "data_dir",
    "db_filename",
    "clock_format",
)


def default_data_dir_path() -> Path:
    return Path.home() / ".local" / "share" / "ttd"


def default_data_dir() -> Path:
    path = default_data_dir_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TTD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=default_data_dir)
    db_filename: str = "ttd.db"
    clock_format: Literal["12h", "24h"] = "24h"

    @field_validator("data_dir", mode="before")
    @classmethod
    def expand_data_dir(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser().resolve()
        if isinstance(value, Path):
            return value.expanduser().resolve()
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        local_path = find_local_config()
        global_path = global_config_path()
        missing_local = global_path.parent / ".missing-local.toml"
        local_source = TomlConfigSettingsSource(
            settings_cls,
            local_path if local_path is not None else missing_local,
        )
        global_source = TomlConfigSettingsSource(settings_cls, global_path)
        return (
            env_settings,
            dotenv_settings,
            local_source,
            global_source,
            init_settings,
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def db_dsn(self) -> str:
        return f"sqlite:{self.db_path}?mode=rwc"


def _env_var_name(key: str) -> str:
    return f"TTD_{key.upper()}"


def _is_env_set(key: str) -> bool:
    return _env_var_name(key) in os.environ


def _toml_serializable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    return value


def _validate_config_key(key: str) -> None:
    if key not in CONFIG_KEYS:
        raise ValidationError(f"Unknown config key: {key!r}")


def validate_config_value(key: str, raw: str) -> object:
    _validate_config_key(key)
    return _coerce_config_value(key, raw)


def _coerce_config_value(key: str, raw: str) -> object:
    current = get_settings().model_dump()
    try:
        validated = Settings.model_validate({**current, key: raw})
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    return getattr(validated, key)


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def resolve_sources(settings: Settings | None = None) -> dict[str, SettingSource]:
    """Return the winning source layer for each v1 config key."""
    _ = settings or get_settings()
    global_data, local_data, _global_path, _local_path = load_merged_toml()

    sources: dict[str, SettingSource] = {}
    for key in CONFIG_KEYS:
        if _is_env_set(key):
            sources[key] = "env"
        elif key in local_data:
            sources[key] = "local"
        elif key in global_data:
            sources[key] = "global"
        else:
            sources[key] = "default"
    return sources


def get_config_value(key: str) -> str:
    _validate_config_key(key)
    value = getattr(get_settings(), key)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def set_config_value(key: str, value: str, *, global_: bool = False) -> Path:
    _validate_config_key(key)
    coerced = _coerce_config_value(key, value)
    path = global_config_path() if global_ else local_config_write_path()
    update_config_file(path, key, _toml_serializable(coerced))
    clear_settings_cache()
    return path


def init_config(
    *,
    data_dir: str,
    db_filename: str,
    clock_format: Literal["12h", "24h"],
    global_: bool = True,
    create_data_dir: bool = True,
) -> Path:
    """Write a full v1 config file after validation."""
    try:
        validated = Settings.model_validate(
            {
                "data_dir": data_dir,
                "db_filename": db_filename,
                "clock_format": clock_format,
            }
        )
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    if create_data_dir:
        validated.data_dir.mkdir(parents=True, exist_ok=True)
    path = global_config_path() if global_ else local_config_write_path()
    payload = {key: _toml_serializable(getattr(validated, key)) for key in CONFIG_KEYS}
    write_toml(path, payload)
    clear_settings_cache()
    return path


def config_target_path(*, global_: bool) -> Path:
    return global_config_path() if global_ else local_config_write_path()


def config_file_has_settings(path: Path) -> bool:
    data = read_toml(path)
    return any(key in data for key in CONFIG_KEYS)
