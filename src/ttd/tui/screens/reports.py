"""Reports: weekly/monthly rollups with activity heat strips and billable value."""

from datetime import date, timedelta
from decimal import Decimal
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Label

from ttd.config.loader import get_settings
from ttd.core.money import format_hours, format_money
from ttd.core.rollup import EntryFacts, amount, rollup_days
from ttd.reporting import periods
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
    ]

    def __init__(self) -> None:
        super().__init__()
        self.report_mode = "week"
        self.period_offset = 0  # periods back from current

    def compose_content(self) -> ComposeResult:
        with Vertical(id="reports"):
            yield Label("", id="report-title", classes="section-title")
            yield ReportChart(id="report-chart")
            yield DataTable(id="report-table", cursor_type="row")
            yield Label("", id="report-total", classes="muted")

    def setup(self) -> None:
        table = self.query_one("#report-table", DataTable)
        table.add_columns("project", "days", "hours", "activity", "value")

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
            if pk(r.project) not in rates:
                rates[pk(r.project)] = await project_svc.effective_rate(r.project)
                labels[pk(r.project)] = f"{r.client.slug}/{r.project.slug}"
                currencies[pk(r.project)] = r.client.currency

        cells = rollup_days(facts)
        groups: dict = {}
        for cell in cells:
            groups.setdefault(cell.project_id, []).append(cell)

        table = self.query_one("#report-table", DataTable)
        table.clear()
        days = period.days()
        day_totals: dict[date, int] = {}
        for f in facts:
            day_totals[f.work_date] = day_totals.get(f.work_date, 0) + f.seconds
        self.query_one("#report-chart", ReportChart).update_data(days, day_totals)
        total_seconds = sum(f.seconds for f in facts)
        total_value = Decimal("0")
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
            if has_rate:
                total_value += value
                any_rate = True
            table.add_row(
                labels[project_id],
                str(len({c.work_date for c in group})),
                format_hours(seconds),
                _heat_strip([by_date.get(d, 0) for d in days]),
                format_money(value, currencies[project_id]) if has_rate else "—",
            )
        self.query_one("#report-title", Label).update(f"{period.label}")
        total = f"total {format_hours(total_seconds)}"
        if any_rate:
            total += f" · {format_money(total_value, 'USD')} billable"
        self.query_one("#report-total", Label).update(
            f"{total}   [dim]w/m switch period · \\[ ] older/newer[/dim]"
        )

    async def action_mode(self, mode: str) -> None:
        self.report_mode = mode
        self.period_offset = 0
        await self.refresh_data()

    async def action_shift(self, delta: int) -> None:
        self.period_offset = max(0, self.period_offset - delta)
        await self.refresh_data()
