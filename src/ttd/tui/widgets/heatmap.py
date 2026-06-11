"""GitHub-style activity heatmap of hours per day — the signature visual."""

from datetime import date, timedelta

from rich.text import Text
from textual.widget import Widget

from ttd.tui.theme import HEAT_RAMP, heat_level

CELL = "▮"
DAY_LABELS = {0: "mon", 2: "wed", 4: "fri"}


class Heatmap(Widget):
    DEFAULT_CSS = """
    Heatmap { height: 9; width: auto; }
    """

    def __init__(self, days: int = 91, **kwargs) -> None:
        super().__init__(**kwargs)
        self.days = days
        self._data: dict[date, int] = {}
        self._today = date.today()

    def update_data(self, by_date: dict[date, int], today: date | None = None) -> None:
        self._data = by_date
        self._today = today or date.today()
        self.refresh()

    def render(self) -> Text:
        today = self._today
        start = today - timedelta(days=self.days - 1)
        start -= timedelta(days=start.weekday())  # align to Monday
        weeks: list[list[date | None]] = []
        cursor = start
        while cursor <= today:
            week = [
                cursor + timedelta(days=i) if cursor + timedelta(days=i) <= today else None
                for i in range(7)
            ]
            weeks.append(week)
            cursor += timedelta(days=7)

        text = Text()
        total = sum(self._data.get(d, 0) for d in self._data if d >= start)
        text.append(f"last {self.days} days", style="bold")
        text.append(f" · {total / 3600:.0f}h\n", style="dim")
        for weekday in range(7):
            text.append(f"{DAY_LABELS.get(weekday, '   '):>3} ", style="dim")
            for week in weeks:
                day = week[weekday]
                if day is None:
                    text.append("  ")
                    continue
                level = heat_level(self._data.get(day, 0))
                style = HEAT_RAMP[level]
                if day == today:
                    style += " bold underline"
                text.append(CELL + " ", style=style)
            text.append("\n")
        return text
