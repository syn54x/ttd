"""Rich formatters for CLI list and detail views."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from rich.table import Table

from ttd.cli.console import muted, stdout
from ttd.core.models.client import Client
from ttd.core.models.enums import BillingMode, enum_value
from ttd.core.models.project import Project
from ttd.core.models.time_entry import TimeEntry


def _short_id(value: UUID | None) -> str:
    return str(value)[:8] if value is not None else "--------"


def format_hours(hours: Decimal) -> str:
    return f"{hours.quantize(Decimal('0.01'))}h"


def print_clients(clients: list[Client]) -> None:
    if not clients:
        muted("No clients.")
        return
    table = Table(title="Clients", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Rate", justify="right")
    table.add_column("Currency", justify="center")
    for client in clients:
        table.add_row(
            _short_id(client.id),
            client.name,
            str(client.default_hourly_rate),
            client.currency,
        )
    stdout.print(table)


def print_projects(projects: list[Project]) -> None:
    if not projects:
        muted("No projects.")
        return
    table = Table(title="Projects", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Client", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Mode")
    table.add_column("Billing", overflow="fold")
    for project in projects:
        mode = enum_value(project.billing_mode)
        if mode == BillingMode.HOURLY:
            billing = "hourly (inherits client rate unless overridden)"
        else:
            billing = f"fixed {project.contract_total} {project.currency}"
        table.add_row(
            _short_id(project.id),
            _short_id(project.client_id),
            project.name,
            mode,
            billing,
        )
    stdout.print(table)


def print_entries(entries: list[TimeEntry]) -> None:
    if not entries:
        muted("No entries.")
        return
    table = Table(title="Time entries", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Project", style="cyan", no_wrap=True)
    table.add_column("Date", no_wrap=True)
    table.add_column("Hours", justify="right", no_wrap=True)
    table.add_column("Capture")
    table.add_column("Billable", no_wrap=True)
    table.add_column("Note", overflow="fold")
    for entry in entries:
        mode = enum_value(entry.entry_mode)
        if mode == "interval" and entry.started_at and entry.ended_at:
            span = (
                f"{entry.started_at.strftime('%H:%M')}-"
                f"{entry.ended_at.strftime('%H:%M')} UTC"
            )
        else:
            span = mode
        billable = "[green]yes[/green]" if entry.billable else "[dim]no[/dim]"
        table.add_row(
            _short_id(entry.id),
            _short_id(entry.project_id),
            str(entry.work_date),
            format_hours(entry.billable_hours),
            span,
            billable,
            entry.note or "",
        )
    stdout.print(table)


def print_entry(entry: TimeEntry) -> None:
    print_entries([entry])
