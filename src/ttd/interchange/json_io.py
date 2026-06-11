import json
from pathlib import Path
from typing import Any

from ttd.core.errors import TtdError
from ttd.interchange.base import Format, register
from ttd.interchange.model import EntryRecord

ENVELOPE_VERSION = 1


def write_json(records: list[EntryRecord], path: Path, meta: dict[str, Any]) -> None:
    payload = {
        "ttd_export": ENVELOPE_VERSION,
        # clients/projects metadata (rates etc.) make JSON the full-fidelity backup
        "clients": meta.get("clients", []),
        "projects": meta.get("projects", []),
        "entries": [
            {**r.to_cells(), "seconds": r.seconds, "billable": r.billable} for r in records
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TtdError(f"{path} is not valid JSON: {exc}") from exc
    if isinstance(payload, dict) and "entries" in payload:
        rows = payload["entries"]
    elif isinstance(payload, list):
        rows = payload  # bare array of row objects
    else:
        raise TtdError(f"{path} doesn't look like a ttd export (no 'entries' key)")
    return [dict(row) for row in rows]


def read_metadata(path: Path) -> dict[str, Any]:
    """Clients/projects metadata from a ttd JSON envelope (empty for other files)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return {"clients": payload.get("clients", []), "projects": payload.get("projects", [])}
    return {}


register(Format("json", ("json",), write_json, read_json))
