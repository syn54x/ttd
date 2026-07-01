"""Two-column theme picker: searchable list + miniature TUI preview."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Rule, Static
from textual.widgets.option_list import Option


class ThemePreview(Static):
    """Representative TUI chrome — reads live theme tokens from the app."""

    DEFAULT_CSS = """
    ThemePreview {
        height: 1fr;
        background: $background;
        border: round $panel;
        padding: 0 1;
    }

    ThemePreview #preview-frame {
        height: 1fr;
    }

    ThemePreview #preview-rail {
        width: 14;
        padding: 1 0 0 1;
        border-right: solid $panel;
    }

    ThemePreview #preview-brand {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    ThemePreview .preview-nav {
        color: $secondary;
    }

    ThemePreview .preview-nav-active {
        color: $accent;
        text-style: bold;
    }

    ThemePreview #preview-content {
        padding: 1;
        width: 1fr;
    }

    ThemePreview .preview-section {
        text-style: bold;
        margin-bottom: 1;
    }

    ThemePreview .preview-header {
        color: $accent;
        text-style: bold;
    }

    ThemePreview .preview-row {
        color: $foreground;
    }

    ThemePreview .preview-muted {
        color: $secondary;
        margin-top: 1;
    }

    ThemePreview Rule {
        color: $panel;
        margin: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="preview-frame"):
            with Vertical(id="preview-rail"):
                yield Label("ttd", id="preview-brand")
                yield Label("1 dashboard", classes="preview-nav-active")
                yield Label("2 log", classes="preview-nav")
                yield Label("3 clients", classes="preview-nav")
            with Vertical(id="preview-content"):
                yield Label("today", classes="preview-section")
                yield Rule(line_style="dashed")
                yield Label("project      time        hours", classes="preview-header")
                yield Label("api rewrite  9:00–11:30  2.50", classes="preview-row")
                yield Label("design       1:00–2:00   1.00", classes="preview-row")
                yield Rule(line_style="dashed")
                yield Label("s start/stop  l log  t theme", classes="preview-muted")


class ThemePickerModal(ModalScreen[str | None]):
    """Browse Textual's theme catalog with a side-by-side TUI mockup."""

    BINDINGS: ClassVar = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "list_up", "Up", show=False),
        Binding("down", "list_down", "Down", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._base_theme = ""
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box theme-picker"):
            yield Label("theme", classes="modal-title")
            with Horizontal(classes="theme-picker-body"):
                with Vertical(classes="theme-picker-list"):
                    yield Input(placeholder="search themes…", id="theme-search")
                    yield OptionList(id="theme-list")
                yield ThemePreview(id="theme-preview")
            with Horizontal(classes="modal-buttons"):
                yield Button("Apply (enter)", variant="primary", id="apply")
                yield Button("Cancel (esc)", id="cancel")

    def on_mount(self) -> None:
        self._base_theme = self.app.theme
        self._rebuild_list(focus_current=True)

    def action_list_up(self) -> None:
        self.query_one("#theme-list", OptionList).action_cursor_up()

    def action_list_down(self) -> None:
        self.query_one("#theme-list", OptionList).action_cursor_down()

    def _grouped_entries(self) -> list[tuple[str, str | None]]:
        """Section headers use theme_id None; selectable rows carry the theme name."""
        query = self.query_one("#theme-search", Input).value.strip().lower()
        themes = self.app.available_themes

        def matches(name: str) -> bool:
            return not query or query in name.lower()

        dark = sorted(name for name, theme in themes.items() if theme.dark and matches(name))
        light = sorted(name for name, theme in themes.items() if not theme.dark and matches(name))

        entries: list[tuple[str, str | None]] = []
        if dark:
            entries.append(("dark", None))
            entries.extend((name, name) for name in dark)
        if light:
            entries.append(("light", None))
            entries.extend((name, name) for name in light)
        return entries

    def _selectable_theme_ids(self) -> list[str]:
        return [theme_id for _, theme_id in self._grouped_entries() if theme_id is not None]

    def _highlight_index(
        self, theme_list: OptionList, selectable: list[str], *, focus_current: bool
    ) -> int:
        if not selectable:
            return 0
        if len(selectable) == 1:
            target = selectable[0]
        elif focus_current and self._base_theme in selectable:
            target = self._base_theme
        elif self._selected in selectable:
            target = self._selected
        else:
            target = selectable[0]
        return next(i for i, option in enumerate(theme_list.options) if option.id == target)

    def _rebuild_list(self, *, focus_current: bool = False) -> None:
        theme_list = self.query_one("#theme-list", OptionList)
        entries = self._grouped_entries()
        theme_list.clear_options()
        if not entries:
            self._selected = None
            return
        for label, theme_id in entries:
            if theme_id is None:
                theme_list.add_option(
                    Option(label, id=f"__header_{label}__", disabled=True),
                )
            else:
                theme_list.add_option(Option(label, id=theme_id))
        selectable = self._selectable_theme_ids()
        highlight = self._highlight_index(theme_list, selectable, focus_current=focus_current)
        theme_list.highlighted = highlight
        self._preview_at(highlight)

    def _preview_at(self, index: int | None) -> None:
        if index is None:
            return
        theme_list = self.query_one("#theme-list", OptionList)
        if index < 0 or index >= theme_list.option_count:
            return
        option = theme_list.get_option_at_index(index)
        if option.id is None or option.disabled or str(option.id).startswith("__header_"):
            return
        self._selected = str(option.id)
        if self._selected in self.app.available_themes:
            self.app.theme = self._selected

    @on(Input.Changed, "#theme-search")
    def _search_changed(self, _event: Input.Changed) -> None:
        self._rebuild_list()

    @on(OptionList.OptionHighlighted, "#theme-list")
    def _highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.disabled or event.option.id is None:
            return
        theme_name = str(event.option.id)
        if theme_name.startswith("__header_"):
            return
        self._selected = theme_name
        if self._selected in self.app.available_themes:
            self.app.theme = self._selected

    @on(OptionList.OptionSelected, "#theme-list")
    def _selected_option(self, _event: OptionList.OptionSelected) -> None:
        self._apply()

    @on(Input.Submitted, "#theme-search")
    def _search_submitted(self) -> None:
        self._apply()

    @on(Button.Pressed, "#apply")
    def _apply_button(self) -> None:
        self._apply()

    @on(Button.Pressed, "#cancel")
    def _cancel_button(self) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.app.theme = self._base_theme
        self.dismiss(None)

    def _apply(self) -> None:
        selectable = self._selectable_theme_ids()
        if self._selected is None or self._selected not in self.app.available_themes:
            if not selectable:
                return
            self._selected = selectable[0]
        self.app.theme = self._selected
        self.dismiss(self._selected)
