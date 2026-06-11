"""Data helpers shared by TUI screens (thin wrappers over services)."""

from datetime import date, datetime, timedelta

from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours, format_money
from ttd.core.rollup import amount as rollup_amount
from ttd.services import entries as entry_svc
from ttd.services import projects as project_svc
from ttd.storage.models import Client, Entry, Project, pk


async def project_options() -> list[tuple[str, str]]:
    """(id 'client/project', pretty label) pairs, default project first."""
    projects = await project_svc.list_projects()
    clients = {c.id: c for c in await Client.all()}
    default = get_settings().defaults.project
    options = []
    for p in projects:
        client = clients.get(p.client_id)
        if client is None:
            continue
        oid = f"{client.slug}/{p.slug}"
        rate = await project_svc.effective_rate(p)
        label = f"{client.slug}/{p.slug}"
        if rate is not None:
            label += f"  ·  {format_money(rate, client.currency)}/h"
        options.append((oid, label, p.slug == default))
    options.sort(key=lambda o: not o[2])
    return [(oid, label) for oid, label, _ in options]


async def split_and_log(payload: dict, *, now: datetime) -> Entry:
    client_slug, project_slug = payload["project"].split("/", 1)
    return await entry_svc.log_entry(
        payload["spec"],
        project_slug,
        client_slug,
        now=now,
        note=payload.get("note", ""),
        settings=get_settings(),
        force=payload.get("force", False),
    )


async def heatmap_data(days: int = 91, today: date | None = None) -> dict[date, int]:
    today = today or date.today()
    start = today - timedelta(days=days + 7)
    rows = await entry_svc.list_entries(date_from=start, date_to=today)
    out: dict[date, int] = {}
    for r in rows:
        out[r.entry.work_date] = out.get(r.entry.work_date, 0) + r.entry.seconds
    return out


async def day_rows(day: date) -> list[entry_svc.EntryRow]:
    return await entry_svc.list_entries(date_from=day, date_to=day)


async def week_seconds(today: date, week_start: str = "monday") -> int:
    offset = today.weekday() if week_start == "monday" else (today.weekday() + 1) % 7
    start = today - timedelta(days=offset)
    rows = await entry_svc.list_entries(date_from=start, date_to=today)
    return sum(r.entry.seconds for r in rows)


async def unbilled_value() -> tuple[int, str]:
    """(total unbilled billable seconds, formatted money across clients)."""
    rows = await entry_svc.list_entries()
    settings = get_settings()
    seconds = 0
    total = None
    for r in rows:
        if r.entry.invoice_id is not None or not r.entry.billable:
            continue
        seconds += r.entry.seconds
        rate = await project_svc.effective_rate(r.project)
        if rate is None:
            rate = settings.business.default_hourly_rate
        value = rollup_amount(r.entry.seconds, rate)
        if value is not None:
            total = (total or 0) + value
    money = format_money(total, "USD") if total is not None else "—"
    return seconds, money


async def client_tree() -> list[dict]:
    """Clients with their projects, rates, and unbilled hours."""
    clients = await Client.all()
    projects = await Project.all()
    out = []
    for client in sorted(clients, key=lambda c: c.name.lower()):
        if client.archived_at is not None:
            continue
        node = {
            "client": client,
            "projects": [],
        }
        for p in sorted(projects, key=lambda p: p.name.lower()):
            if p.client_id != client.id or p.archived_at is not None:
                continue
            rate = await project_svc.effective_rate(p)
            unbilled = await project_svc.entry_seconds(p, uninvoiced_only=True)
            node["projects"].append(
                {
                    "project": p,
                    "rate": format_money(rate, client.currency) if rate else "—",
                    "unbilled": format_hours(unbilled),
                }
            )
        out.append(node)
    return out


async def delete_entry_by_id(entry_id) -> None:
    entry = await Entry.get_or_none(entry_id)
    if entry is None:
        raise TtdError("Entry vanished")
    if entry.invoice_id is not None:
        raise TtdError("Entry is on an invoice — void it first")
    await entry.delete()


def hours_for_row(entry: Entry) -> str:
    when = (
        f"{entry.started_at:%-I:%M%p}–{entry.ended_at:%-I:%M%p}".lower()
        if entry.started_at and entry.ended_at
        else "—"
    )
    return when


__all__ = [
    "client_tree",
    "day_rows",
    "delete_entry_by_id",
    "heatmap_data",
    "hours_for_row",
    "pk",
    "project_options",
    "split_and_log",
    "unbilled_value",
    "week_seconds",
]
