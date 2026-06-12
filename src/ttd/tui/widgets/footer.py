"""A Footer that wraps onto extra rows instead of cutting bindings off.

Textual's built-in Footer is a single-row horizontal strip: bindings that
don't fit the terminal width are silently clipped, with no indication that
shortcuts exist beyond the edge. AdaptiveFooter measures its keys after
layout and, when they overflow, recomposes them into as many rows as the
width requires — every binding stays visible at any terminal size.
"""

from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widget import Widget
from textual.widgets import Footer

# Private import: FooterLabel is the group-description widget Footer emits
# after each KeyGroup. The wrap tests in tests/test_tui/test_footer.py fail
# loudly if a Textual upgrade moves or renames it.
from textual.widgets._footer import FooterLabel


class FooterRow(HorizontalGroup):
    """One row of footer keys when the footer is wrapped."""


class AdaptiveFooter(Footer):
    DEFAULT_CSS = """
    AdaptiveFooter.-wrapped {
        layout: vertical;
        height: auto;
    }
    AdaptiveFooter FooterRow {
        height: 1;
        width: 1fr;
    }
    AdaptiveFooter.-wrapped FooterKey.-command-palette {
        dock: none;
        border-left: none;
    }
    """

    def __init__(
        self,
        *children: Widget,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
        show_command_palette: bool = True,
        compact: bool = False,
    ) -> None:
        super().__init__(
            *children,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
            show_command_palette=show_command_palette,
            compact=compact,
        )
        # A unit is the smallest group of widgets that must stay on one row:
        # a lone FooterKey, or a KeyGroup plus its trailing FooterLabel.
        self._units: list[list[Widget]] = []
        self._row_plan: list[int] = []  # unit count per row; [] or [n] = flat

    def compose(self) -> ComposeResult:
        units: list[list[Widget]] = []
        for widget in super().compose():
            if isinstance(widget, FooterLabel) and units:
                units[-1].append(widget)
            else:
                units.append([widget])
        self._units = units

        plan = self._row_plan
        # A stale plan (bindings changed since it was computed) composes flat;
        # the post-refresh measurement pass then computes a fresh plan.
        wrapped = len(plan) > 1 and sum(plan) == len(units)
        self.set_class(wrapped, "-wrapped")
        if not wrapped:
            for unit in units:
                yield from unit
            return
        index = 0
        for count in plan:
            with FooterRow():
                for unit in units[index : index + count]:
                    yield from unit
            index += count

    async def recompose(self) -> None:
        await super().recompose()
        # Bindings may have changed (screen switch); re-measure once the new
        # keys have been laid out and painted.
        self.call_after_refresh(self._replan)

    def on_resize(self) -> None:
        self._replan()

    def _replan(self) -> None:
        """Re-measure units against the current width; recompose if the row
        assignment changes."""
        available = self.container_size.width
        if not self._units or available <= 0:
            return
        widths = [
            sum(w.outer_size.width + w.styles.margin.width for w in unit) for unit in self._units
        ]
        if 0 in widths:  # not laid out yet; a later resize/refresh replans
            return
        plan = self._fit(widths, available)
        if plan != self._row_plan:
            self._row_plan = plan
            self.call_after_refresh(self.recompose)

    @staticmethod
    def _fit(widths: list[int], available: int) -> list[int]:
        """Greedy row assignment: unit count per row, preserving order."""
        plan: list[int] = []
        count = used = 0
        for width in widths:
            if count and used + width > available:
                plan.append(count)
                count = used = 0
            count += 1
            used += width
        plan.append(count)
        return plan
