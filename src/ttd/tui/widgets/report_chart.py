"""Plotext bar chart of total hours per day for the reports screen."""

from datetime import date

from textual.color import Color
from textual_plotext import PlotextPlot


class ReportChart(PlotextPlot):
    """Aggregate hours-per-day bars for the selected report period."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._days: list[date] = []
        self._hours: list[float] = []

    def update_data(self, days: list[date], by_date: dict[date, int]) -> None:
        self._days = days
        self._hours = [by_date.get(d, 0) / 3600 for d in days]
        self._replot()

    def _labels(self) -> list[str]:
        if len(self._days) <= 7:
            return [d.strftime("%a").lower() for d in self._days]
        return [str(d.day) for d in self._days]

    def _replot(self) -> None:
        plt = self.plt
        plt.clear_data()
        # L-shaped axes only: the ttd look is thin rules, not boxes
        plt.xaxes(True, False)
        plt.yaxes(True, False)
        if self._days:
            accent = Color.parse(self.app.theme_variables.get("accent", "#ffb000")).rgb
            # narrower relative width when bars are dense, so a gap cell survives
            # plotext's rounding to whole terminal cells
            width = 3 / 5 if len(self._days) <= 7 else 1 / 4
            plt.bar(self._labels(), self._hours, color=accent, width=width)
            if not any(self._hours):
                plt.ylim(0, 1)
        self.refresh()
