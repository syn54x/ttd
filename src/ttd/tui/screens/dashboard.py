"""Dashboard: big timer, today's entries, week bar, activity heatmap."""

from datetime import date, datetime

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Label, Rule

from ttd.config.loader import get_settings
from ttd.core.money import format_hours
from ttd.services import timer as timer_svc
from ttd.tui._data import day_rows, heatmap_data, hours_for_row, unbilled_value, week_seconds
from ttd.tui.screens._base import TtdScreen
from ttd.tui.widgets.big_timer import BigTimer
from ttd.tui.widgets.heatmap import Heatmap


class DashboardScreen(TtdScreen):
    nav_id = "dashboard"

    def compose_content(self) -> ComposeResult:
        with Vertical(id="dashboard"):
            yield BigTimer(id="big-timer")
            yield Rule(line_style="dashed")
            yield Label("", id="today-title", classes="section-title")
            yield DataTable(id="today-table", cursor_type="row", zebra_stripes=False)
            yield Rule(line_style="dashed")
            yield Heatmap(id="heatmap")
            yield Label("", id="dash-summary", classes="muted")

    def setup(self) -> None:
        table = self.query_one("#today-table", DataTable)
        table.add_columns("project", "time", "hours", "note")
        self.set_interval(1.0, self._tick)

    async def _tick(self) -> None:
        status = await timer_svc.timer_status(now=datetime.now())
        self.query_one("#big-timer", BigTimer).show_status(status, datetime.now())

    async def render_data(self) -> None:
        now = datetime.now()
        today = now.date()
        status = await timer_svc.timer_status(now=now)
        self.query_one("#big-timer", BigTimer).show_status(status, now)

        rows = await day_rows(today)
        table = self.query_one("#today-table", DataTable)
        table.clear()
        for r in rows:
            table.add_row(
                f"{r.client.slug}/{r.project.slug}",
                hours_for_row(r.entry),
                format_hours(r.entry.seconds),
                r.entry.note,
                key=str(r.entry.id),
            )
        self.query_one("#today-title", Label).update(
            f"today · {today:%A %b %-d} · {len(rows)} entr{'y' if len(rows) == 1 else 'ies'}"
        )

        self.query_one("#heatmap", Heatmap).update_data(await heatmap_data(), date.today())

        week = await week_seconds(today, get_settings().display.week_start)
        unbilled_secs, unbilled_money = await unbilled_value()
        self.query_one("#dash-summary", Label).update(
            f"this week {format_hours(week)} · unbilled {format_hours(unbilled_secs)}"
            f" ({unbilled_money})"
        )
