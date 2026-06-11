"""Persisted enums. Stored as text columns, not native DB enums."""

from enum import StrEnum


class EntrySource(StrEnum):
    TIMER = "timer"
    LOG = "log"
    IMPORT = "import"
    TUI = "tui"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    VOID = "void"


def enum_value(member: StrEnum | str) -> str:
    """Return the persisted string for an enum-or-string value.

    Ferro may hydrate ``FerroField(db_type="text")`` enum columns as plain
    ``str`` on cold reads; use this when formatting loaded rows.
    """
    return member if isinstance(member, str) else member.value
