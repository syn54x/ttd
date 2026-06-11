"""Modal dialogs: quick log (with live NL parse preview), timer start, confirm."""

from datetime import datetime
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from ttd.config.loader import get_settings
from ttd.core.errors import ParseError
from ttd.core.money import format_hours
from ttd.parsing.resolve import resolve_entry


class ConfirmModal(ModalScreen[bool]):
    """Generic yes/no."""

    BINDINGS: ClassVar = [("escape", "dismiss(False)", "Cancel"), ("y", "dismiss(True)", "Yes")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self.message, classes="modal-title")
            with Horizontal(classes="modal-buttons"):
                yield Button("Yes (y)", variant="warning", id="yes")
                yield Button("Cancel (esc)", id="no")

    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def _no(self) -> None:
        self.dismiss(False)


class PickerModal(ModalScreen[str | None]):
    """Pick one option (used for projects, clients, …)."""

    BINDINGS: ClassVar = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, title: str, options: list[tuple[str, str]]) -> None:
        """options: (id, label) pairs."""
        super().__init__()
        self.title_text = title
        self.options = options

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self.title_text, classes="modal-title")
            yield OptionList(*(Option(label, id=oid) for oid, label in self.options))

    @on(OptionList.OptionSelected)
    def _picked(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)


class QuickLogModal(ModalScreen[dict | None]):
    """NL time entry with live parse preview — the signature interaction."""

    BINDINGS: ClassVar = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, projects: list[tuple[str, str]], initial_spec: str = "") -> None:
        """projects: (id 'client/project', label) pairs."""
        super().__init__()
        self.projects = projects
        self.initial_spec = initial_spec
        self.selected_project: str | None = self.projects[0][0] if self.projects else None

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box wide"):
            yield Label("log time", classes="modal-title")
            yield Input(
                value=self.initial_spec,
                placeholder="today 9am to 5pm · yesterday 2h · monday 1pm for 3 hours",
                id="spec",
            )
            yield Static("", id="preview")
            yield OptionList(*(Option(label, id=oid) for oid, label in self.projects), id="project")
            yield Input(placeholder="note (optional)", id="note")
            with Horizontal(classes="modal-buttons"):
                yield Button("Log it", variant="primary", id="submit")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._update_preview(self.initial_spec)
        if self.projects:
            self.query_one("#project", OptionList).highlighted = 0

    @on(Input.Changed, "#spec")
    def _spec_changed(self, event: Input.Changed) -> None:
        self._update_preview(event.value)

    def _update_preview(self, spec: str) -> None:
        preview = self.query_one("#preview", Static)
        if not spec.strip():
            preview.update("[dim]…the preview shows what will be logged[/dim]")
            return
        try:
            r = resolve_entry(spec, datetime.now(), get_settings().parsing)
        except ParseError as exc:
            preview.update(f"[red]✗ {exc}[/red]")
            return
        if r.started_at and r.ended_at:
            when = f"{r.started_at:%-I:%M%p} – {r.ended_at:%-I:%M%p}".lower()
        else:
            when = "no clock times"
        preview.update(
            f"[#ffb000]✓[/#ffb000] {r.work_date:%a %b %-d} · {when} · "
            f"[bold]{format_hours(r.seconds)}[/bold]"
        )

    @on(OptionList.OptionHighlighted, "#project")
    def _project_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self.selected_project = event.option.id

    @on(OptionList.OptionSelected, "#project")
    def _project_selected(self, event: OptionList.OptionSelected) -> None:
        self.selected_project = event.option.id
        self._submit()

    @on(Input.Submitted)
    def _input_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#submit")
    def _button_submit(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel")
    def _button_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        spec = self.query_one("#spec", Input).value.strip()
        if not spec:
            return
        try:
            resolve_entry(spec, datetime.now(), get_settings().parsing)
        except ParseError:
            return  # preview already shows the problem
        if self.selected_project is None:
            return
        self.dismiss(
            {
                "spec": spec,
                "project": self.selected_project,
                "note": self.query_one("#note", Input).value.strip(),
            }
        )
