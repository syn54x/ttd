"""The interchange row: one entry as it appears in every export format.

Column order is the contract — all four formats write exactly these columns.
``seconds`` is authoritative; ``hours`` is a human-friendly derivation that
importers fall back to for foreign spreadsheets.
"""

from datetime import date as date_t
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

COLUMNS = [
    "uid",
    "client",
    "project",
    "date",
    "start",
    "end",
    "hours",
    "seconds",
    "note",
    "tags",
    "billable",
    "invoice_number",
]

TRUTHY = {"true", "1", "yes", "y", "x"}
FALSY = {"false", "0", "no", "n", ""}


class EntryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str = ""  # UUID string when ttd-born; may be blank in foreign files
    client: str
    project: str
    date: date_t
    start: time | None = None
    end: time | None = None
    seconds: int
    note: str = ""
    tags: str = ""
    billable: bool = True
    invoice_number: str = ""  # informational; imports never re-link invoices

    @field_validator("client", "project", mode="before")
    @classmethod
    def _required_str(cls, v: object) -> str:
        text = str(v).strip() if v is not None else ""
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("uid", "note", "tags", "invoice_number", mode="before")
    @classmethod
    def _optional_str(cls, v: object) -> str:
        return str(v) if v is not None else ""

    @field_validator("uid", mode="after")
    @classmethod
    def _uid(cls, v: str) -> str:
        return v.strip()

    @field_validator("date", mode="before")
    @classmethod
    def _date(cls, v: object) -> object:
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            return date_t.fromisoformat(v.strip())
        return v

    @field_validator("start", "end", mode="before")
    @classmethod
    def _time(cls, v: object) -> object:
        if v is None or isinstance(v, time):
            return v
        if isinstance(v, datetime):
            return v.time()
        text = str(v).strip()
        if not text:
            return None
        return time.fromisoformat(text)

    @field_validator("seconds", mode="before")
    @classmethod
    def _seconds(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return 0  # caught by range check below; hours fallback happens in from_raw
        if isinstance(v, str):
            return int(float(v))
        if isinstance(v, float):
            return int(v)
        return v

    @field_validator("seconds", mode="after")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("seconds must be positive")
        return v

    @field_validator("billable", mode="before")
    @classmethod
    def _billable(cls, v: object) -> object:
        if isinstance(v, str):
            lowered = v.strip().lower()
            if lowered in TRUTHY:
                return True
            if lowered in FALSY:
                return False
            raise ValueError(f"not a boolean: {v!r}")
        return v if v is not None else True

    @property
    def hours(self) -> Decimal:
        return (Decimal(self.seconds) / 3600).quantize(Decimal("0.01"))

    @property
    def uuid(self) -> UUID | None:
        try:
            return UUID(self.uid) if self.uid else None
        except ValueError:
            return None

    @property
    def content_key(self) -> tuple:
        """Dedupe key for uid-less rows."""
        return (self.client, self.project, self.date, self.start, self.end, self.seconds, self.note)

    def to_cells(self) -> dict[str, Any]:
        """Column → primitive value, in the canonical formats."""
        return {
            "uid": self.uid,
            "client": self.client,
            "project": self.project,
            "date": self.date.isoformat(),
            "start": self.start.isoformat() if self.start else "",
            "end": self.end.isoformat() if self.end else "",
            "hours": f"{self.hours}",
            "seconds": self.seconds,
            "note": self.note,
            "tags": self.tags,
            "billable": "true" if self.billable else "false",
            "invoice_number": self.invoice_number,
        }


def from_raw(raw: dict[str, Any]) -> EntryRecord:
    """Validate a raw row dict; falls back to ``hours`` when seconds is blank."""
    data = {k: raw.get(k) for k in COLUMNS if k != "hours"}
    seconds = raw.get("seconds")
    if seconds in (None, "", 0):
        hours = raw.get("hours")
        if hours not in (None, ""):
            data["seconds"] = round(float(str(hours)) * 3600)
    return EntryRecord.model_validate(data)
