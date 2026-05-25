"""Ledger enumerations."""

from __future__ import annotations

from enum import StrEnum


class BillingMode(StrEnum):
    """How a project is billed commercially."""

    HOURLY = "hourly"
    FIXED_PRICE = "fixed_price"


class EntryMode(StrEnum):
    """How a time entry was captured."""

    DURATION = "duration"
    INTERVAL = "interval"


def enum_value(member: BillingMode | EntryMode | str) -> str:
    """Return the persisted string for a ledger enum.

    Ferro may hydrate ``FerroField(db_type="text")`` enum columns as plain
    ``str`` on read. Use this (or ``== BillingMode.HOURLY``) instead of
    ``.value`` when formatting or logging loaded rows.
    """
    return member if isinstance(member, str) else member.value
