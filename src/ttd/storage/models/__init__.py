"""Ferro models. Importing this package registers all model metadata."""

from typing import Protocol
from uuid import UUID

from ttd.storage.models.client import Client
from ttd.storage.models.entry import Entry
from ttd.storage.models.enums import EntrySource, InvoiceStatus, enum_value
from ttd.storage.models.invoice import Invoice, InvoiceLine
from ttd.storage.models.project import Project
from ttd.storage.models.tax_payment import TaxPayment
from ttd.storage.models.timer import TIMER_SINGLETON_ID, TimerState


class _HasId(Protocol):
    id: UUID | None


def pk(model: _HasId) -> UUID:
    """The primary key of a persisted row (typed non-None for ty's benefit)."""
    assert model.id is not None, "model has not been saved"
    return model.id


__all__ = [
    "TIMER_SINGLETON_ID",
    "Client",
    "Entry",
    "EntrySource",
    "Invoice",
    "InvoiceLine",
    "InvoiceStatus",
    "Project",
    "TaxPayment",
    "TimerState",
    "enum_value",
]
