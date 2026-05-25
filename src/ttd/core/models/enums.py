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
