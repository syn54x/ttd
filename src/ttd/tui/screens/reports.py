"""Reports: weekly/monthly rollups with activity heat strips and billable value."""

from datetime import date, timedelta
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Label

from ttd.config.loader import get_settings
from ttd.core.money import format_hours, format_money
from ttd.core.rollup import EntryFacts, amount, rollup_days
from ttd.core.taxes import compute_set_aside
from ttd.reporting import periods
from ttd.reporting.render import (
    entry_amount,
    entry_detail_label,
    entry_flags_markup,
    group_entries_by_project,
    truncate_note,
)
from ttd.services import entries as entry_svc
from ttd.services import projects as project_svc
from ttd.tui._data import pk
from ttd.tui.screens._base import PREV_NEXT_GROUP, TtdScreen
from ttd.tui.theme import HEAT_RAMP, heat_level
from ttd.tui.widgets.heatmap import CELL
from ttd.tui.widgets.report_chart import ReportChart


def _heat_strip(values: list[int]) -> str:
    """One cell per day, colored by the same intensity ramp as the heatmap."""
    out = []
    for v in values[-31:]:
        if v <= 0:
            out.append("[dim]·[/dim]")
        else:
            out.append(f"[{HEAT_RAMP[heat_level(v)]}]{CELL}[/]")
    return "".join(out)


MODE_GROUP = Binding.Group("mode", compact=True)


class ReportsScreen(TtdScreen):
    nav_id = "reports"

    BINDINGS: ClassVar = [
        *TtdScreen.BINDINGS,
        Binding("w", "mode('week')", "week", group=MODE_GROUP),
        Binding("m", "mode('month')", "month", group=MODE_GROUP),
        Binding("left_square_bracket", "shift(-1)", "prev", group=PREV_NEXT_GROUP),
        Binding("right_square_bracket", "shift(1)", "next", group=PREV_NEXT_GROUP),
        Binding("enter", "toggle_expand", "expand", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.report_mode = "week"
        self.period_offset = 0  # periods back from current
        self._expanded_projects: set[UUID] = set()

    def compose_content(self) -> ComposeResult:
        with Vertical(id="reports"):
            yield Label("", id="report-title", classes="section-title")
            yield ReportChart(id="report-chart")
            yield DataTable(id="report-table", cursor_type="row")
            yield Label("", id="report-total", classes="muted")

    def setup(self) -> None:
        self._table_columns: tuple[str, ...] = ()

    def _period(self) -> periods.Period:
        today = date.today()
        if self.report_mode == "week":
            anchor = today - timedelta(days=7 * self.period_offset)
            return periods.week_period(anchor, get_settings().display.week_start)
        anchor = today
        for _ in range(self.period_offset):
            anchor = anchor.replace(day=1) - timedelta(days=1)
        return periods.month_period(anchor)

    async def render_data(self) -> None:
        period = self._period()
        settings = get_settings()
        rows = await entry_svc.list_entries(date_from=period.start, date_to=period.end)
        entries_by_project = group_entries_by_project(rows)

        facts, rates, labels, currencies = [], {}, {}, {}
        for r in rows:
            facts.append(
                EntryFacts(
                    pk(r.project),
                    pk(r.client),
                    r.entry.work_date,
                    r.entry.seconds,
                    r.entry.billable,
                    r.entry.note,
                    r.entry.invoice_id is not None,
                )
            )
            pid = pk(r.project)
            if pid not in rates:
                rates[pid] = await project_svc.effective_rate(r.project)
                labels[pid] = f"{r.client.slug}/{r.project.slug}"
                currencies[pid] = r.client.currency

        cells = rollup_days(facts)
        groups: dict = {}
        for cell in cells:
            groups.setdefault(cell.project_id, []).append(cell)

        set_aside_rate = settings.tax.set_aside_rate
        columns = ("project", "days", "hours", "activity", "value")
        if set_aside_rate > 0:
            columns += ("est. tax", "take-home")
        table = self.query_one("#report-table", DataTable)
        if columns != self._table_columns:
            table.clear(columns=True)
            table.add_columns(*columns)
            self._table_columns = columns
        table.clear()
        days = period.days()
        day_totals: dict[date, int] = {}
        for f in facts:
            day_totals[f.work_date] = day_totals.get(f.work_date, 0) + f.seconds
        self.query_one("#report-chart", ReportChart).update_data(days, day_totals)
        total_seconds = sum(f.seconds for f in facts)
        total_value = Decimal("0")
        total_tax = Decimal("0")
        any_rate = False
        for project_id, group in sorted(
            groups.items(), key=lambda kv: -sum(c.seconds for c in kv[1])
        ):
            seconds = sum(c.seconds for c in group)
            by_date = {c.work_date: 0 for c in group}
            for c in group:
                by_date[c.work_date] += c.seconds
            value = Decimal("0")
            has_rate = False
            for c in group:
                v = amount(c.billed_seconds(settings.billing), rates[project_id])
                if v is not None:
                    value += v
                    has_rate = True
            tax = compute_set_aside(value, set_aside_rate)
            expanded = project_id in self._expanded_projects
            prefix = "▾ " if expanded else "▸ "
            row = [
                prefix + labels[project_id],
                str(len({c.work_date for c in group})),
                format_hours(seconds),
                _heat_strip([by_date.get(d, 0) for d in days]),
                format_money(value, currencies[project_id]) if has_rate else "—",
            ]
            if set_aside_rate > 0:
                row += (
                    [
                        format_money(tax, currencies[project_id]),
                        format_money(value - tax, currencies[project_id]),
                    ]
                    if has_rate
                    else ["—", "—"]
                )
            if has_rate:
                total_value += value
                total_tax += tax
                any_rate = True
            table.add_row(*row, key=f"p:{project_id}")
            if expanded:
                rate = rates[project_id]
                currency = currencies[project_id]
                for r in entries_by_project.get(project_id, []):
                    entry = r.entry
                    entry_value = entry_amount(entry, rate, settings.billing)
                    hours = format_hours(entry.seconds) + entry_flags_markup(entry)
                    sub = [
                        f"  [dim]{entry_detail_label(entry)}[/dim]",
                        "—",
                        hours,
                        truncate_note(entry.note),
                        format_money(entry_value, currency) if entry_value is not None else "—",
                    ]
                    if set_aside_rate > 0:
                        sub += ["—", "—"]
                    table.add_row(*sub, key=f"e:{entry.id}")

        self.query_one("#report-title", Label).update(f"{period.label}")
        total = f"total {format_hours(total_seconds)}"
        if any_rate:
            total += f" · {format_money(total_value, 'USD')} billable"
            if set_aside_rate > 0:
                total += (
                    f" · {format_money(total_tax, 'USD')} est. tax"
                    f" · {format_money(total_value - total_tax, 'USD')} take-home"
                )
        self.query_one("#report-total", Label).update(
            f"{total}   [dim]Enter expand · w/m switch period · \\[ ] older/newer[/dim]"
        )

    async def action_toggle_expand(self) -> None:
        table = self.query_one("#report-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return
        raw_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key.value
        key = str(raw_key) if raw_key is not None else ""
        if not key.startswith("p:"):
            return
        project_id = UUID(key.removeprefix("p:"))
        if project_id in self._expanded_projects:
            self._expanded_projects.discard(project_id)
        else:
            self._expanded_projects.add(project_id)
        await self.refresh_data()

    async def action_mode(self, mode: str) -> None:
        self.report_mode = mode
        self.period_offset = 0
        self._expanded_projects.clear()
        await self.refresh_data()

    async def action_shift(self, delta: int) -> None:
        self.period_offset = max(0, self.period_offset - delta)
        self._expanded_projects.clear()
        await self.refresh_data()
