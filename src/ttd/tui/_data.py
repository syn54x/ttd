"""Data helpers shared by TUI screens (thin wrappers over services)."""

from datetime import date, datetime, timedelta

from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours, format_money
from ttd.reporting.render import entry_time_label
from ttd.services import clients as client_svc
from ttd.services import entries as entry_svc
from ttd.services import projects as project_svc
from ttd.storage.db import in_db_session
from ttd.storage.models import Entry, pk


@in_db_session
async def project_options() -> list[tuple[str, str]]:
    """(id 'client/project', pretty label) pairs, default project first."""
    projects = await project_svc.list_projects()
    clients = {c.id: c for c in await client_svc.list_clients()}
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


@in_db_session
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


@in_db_session
async def heatmap_data(days: int = 91, today: date | None = None) -> dict[date, int]:
    today = today or date.today()
    start = today - timedelta(days=days + 7)
    rows = await entry_svc.list_entries(date_from=start, date_to=today)
    out: dict[date, int] = {}
    for r in rows:
        out[r.entry.work_date] = out.get(r.entry.work_date, 0) + r.entry.seconds
    return out


@in_db_session
async def day_rows(day: date) -> list[entry_svc.EntryRow]:
    return await entry_svc.list_entries(date_from=day, date_to=day)


@in_db_session
async def week_seconds(today: date, week_start: str = "monday") -> int:
    from ttd.services import summary as summary_svc

    return await summary_svc.week_total(today, week_start)


@in_db_session
async def unbilled_value() -> tuple[int, str]:
    """(total unbilled billable seconds, formatted money across clients)."""
    from ttd.services import summary as summary_svc

    seconds, total = await summary_svc.unbilled_totals()
    money = format_money(total, "USD") if total is not None else "—"
    return seconds, money


@in_db_session
async def client_tree() -> list[dict]:
    """Clients with their projects, rates, and unbilled hours."""
    clients = await client_svc.list_clients()
    projects = await project_svc.list_projects()
    out = []
    for client in clients:
        node = {
            "client": client,
            "projects": [],
        }
        for p in sorted(
            (p for p in projects if p.client_id == client.id),
            key=lambda p: p.name.lower(),
        ):
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


@in_db_session
async def delete_entry_by_id(entry_id) -> None:
    entry = await Entry.get_or_none(entry_id)
    if entry is None:
        raise TtdError("Entry vanished")
    if entry.invoice_id is not None:
        raise TtdError("Entry is on an invoice — void it first")
    await entry.delete()


def hours_for_row(entry: Entry) -> str:
    return entry_time_label(entry)


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
