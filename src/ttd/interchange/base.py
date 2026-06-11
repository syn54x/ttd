"""Format registry: extension → reader/writer pair."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ttd.core.errors import TtdError
from ttd.interchange.model import EntryRecord

# Writers take validated records; readers return raw row dicts that the
# importer validates (so one bad row doesn't kill the file).
Writer = Callable[[list[EntryRecord], Path, dict[str, Any]], None]
Reader = Callable[[Path], list[dict[str, Any]]]


@dataclass(frozen=True)
class Format:
    name: str
    extensions: tuple[str, ...]
    writer: Writer
    reader: Reader


_REGISTRY: dict[str, Format] = {}


def register(fmt: Format) -> None:
    for ext in fmt.extensions:
        _REGISTRY[ext] = fmt
    _REGISTRY[fmt.name] = fmt


def detect_format(path: Path, override: str | None = None) -> Format:
    key = override.lower().lstrip(".") if override else path.suffix.lower().lstrip(".")
    if not key:
        raise TtdError(f"Can't infer format for '{path}' — pass --format csv|json|xlsx|numbers")
    fmt = _REGISTRY.get(key)
    if fmt is None:
        known = ", ".join(sorted({f.name for f in _REGISTRY.values()}))
        raise TtdError(f"Unsupported format '{key}' (known: {known})")
    return fmt


def all_formats() -> list[str]:
    return sorted({f.name for f in _REGISTRY.values()})
