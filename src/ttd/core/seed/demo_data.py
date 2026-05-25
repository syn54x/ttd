"""Declarative demo ledger data for local development."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ttd.core.models.enums import BillingMode

# Used to detect whether demo data is already present.
MARKER_CLIENT_NAME = "Northwind Studio"

DEMO_CLIENT_NAMES = frozenset({"Northwind Studio", "Summit Labs"})


@dataclass(frozen=True, slots=True)
class DemoDurationEntry:
    work_date: date
    hours: Decimal
    note: str | None = None
    billable: bool = True


@dataclass(frozen=True, slots=True)
class DemoIntervalEntry:
    work_date: date
    started: str
    ended: str
    note: str | None = None
    billable: bool = True


@dataclass(frozen=True, slots=True)
class DemoProject:
    name: str
    billing_mode: BillingMode
    hourly_rate: Decimal | None = None
    currency: str | None = None
    contract_total: Decimal | None = None
    soft_max_hours: Decimal | None = None
    duration_entries: tuple[DemoDurationEntry, ...] = ()
    interval_entries: tuple[DemoIntervalEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class DemoClient:
    name: str
    default_hourly_rate: Decimal
    currency: str
    projects: tuple[DemoProject, ...]


DEMO_LEDGER: tuple[DemoClient, ...] = (
    DemoClient(
        name="Northwind Studio",
        default_hourly_rate=Decimal("125"),
        currency="USD",
        projects=(
            DemoProject(
                name="Monthly retainer",
                billing_mode=BillingMode.HOURLY,
                soft_max_hours=Decimal("40"),
                duration_entries=(
                    DemoDurationEntry(
                        date(2026, 5, 6),
                        Decimal("3.5"),
                        note="Sprint planning",
                    ),
                    DemoDurationEntry(
                        date(2026, 5, 13),
                        Decimal("4"),
                        note="Feature implementation",
                    ),
                    DemoDurationEntry(
                        date(2026, 5, 20),
                        Decimal("2.25"),
                        note="Code review",
                    ),
                ),
            ),
            DemoProject(
                name="Internal docs",
                billing_mode=BillingMode.HOURLY,
                duration_entries=(
                    DemoDurationEntry(
                        date(2026, 5, 8),
                        Decimal("1.5"),
                        note="Runbook updates",
                    ),
                ),
            ),
        ),
    ),
    DemoClient(
        name="Summit Labs",
        default_hourly_rate=Decimal("200"),
        currency="USD",
        projects=(
            DemoProject(
                name="Platform API",
                billing_mode=BillingMode.HOURLY,
                hourly_rate=Decimal("175"),
                currency="USD",
                interval_entries=(
                    DemoIntervalEntry(
                        date(2026, 5, 14),
                        "09:30",
                        "12:00",
                        note="Auth endpoint hardening",
                    ),
                    DemoIntervalEntry(
                        date(2026, 5, 16),
                        "14:00",
                        "16:30",
                        note="Pagination + filters",
                    ),
                ),
            ),
            DemoProject(
                name="Data migration",
                billing_mode=BillingMode.FIXED_PRICE,
                contract_total=Decimal("15000"),
                currency="USD",
                duration_entries=(
                    DemoDurationEntry(
                        date(2026, 5, 7),
                        Decimal("6"),
                        note="Schema mapping workshop",
                    ),
                    DemoDurationEntry(
                        date(2026, 5, 21),
                        Decimal("5.5"),
                        note="Dry-run import",
                    ),
                ),
            ),
        ),
    ),
)
