"""Generic form modal — the TUI's counterpart to the CLI's interactive_fill.

Declare fields, get back a dict of values (or None on cancel). Serves the
client/project forms, the entry editor, and the invoice period prompt.
"""

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, ClassVar, Literal

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch


@dataclass
class FormField:
    name: str
    label: str
    kind: Literal["text", "spec", "select", "toggle"] = "text"
    value: Any = None  # prefill
    choices: list[tuple[str, str]] = dc_field(default_factory=list)  # select: (id, label)
    validate: Callable[[str], bool | str] | None = None
    placeholder: str = ""
    preview: Callable[[str], str] | None = None  # spec fields: live line below
    required: bool = False


class FormModal(ModalScreen[dict | None]):
    BINDINGS: ClassVar = [
        ("escape", "dismiss(None)", "cancel"),
        ("ctrl+s", "save", "save"),
    ]

    def __init__(self, title: str, fields: list[FormField]) -> None:
        super().__init__()
        self.title_text = title
        self.fields = fields

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box wide form"):
            yield Label(self.title_text, classes="modal-title")
            with VerticalScroll(classes="form-fields"):
                for f in self.fields:
                    if f.kind == "toggle":
                        with Horizontal(classes="form-toggle-row"):
                            yield Switch(value=bool(f.value), id=f"field-{f.name}")
                            yield Label(f.label, classes="field-label")
                        continue
                    yield Label(f.label, classes="field-label")
                    if f.kind == "select":
                        yield Select(
                            ((label, oid) for oid, label in f.choices),
                            value=f.value if f.value is not None else Select.NULL,
                            allow_blank=f.value is None,
                            id=f"field-{f.name}",
                        )
                    else:
                        yield Input(
                            value="" if f.value is None else str(f.value),
                            placeholder=f.placeholder,
                            id=f"field-{f.name}",
                        )
                        if f.kind == "spec" and f.preview is not None:
                            yield Static("", id=f"preview-{f.name}", classes="field-preview")
            yield Static("", id="form-error", classes="form-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Save (ctrl+s)", variant="primary", id="save")
                yield Button("Cancel (esc)", id="cancel")

    def on_mount(self) -> None:
        for f in self.fields:
            if f.kind == "spec" and f.preview is not None:
                self._update_preview(f, str(f.value or ""))

    def _field(self, name: str) -> FormField:
        return next(f for f in self.fields if f.name == name)

    @on(Input.Changed)
    def _changed(self, event: Input.Changed) -> None:
        name = (event.input.id or "").removeprefix("field-")
        try:
            f = self._field(name)
        except StopIteration:
            return
        if f.kind == "spec" and f.preview is not None:
            self._update_preview(f, event.value)

    def _update_preview(self, f: FormField, raw: str) -> None:
        preview = self.query_one(f"#preview-{f.name}", Static)
        if not raw.strip():
            preview.update("")
            return
        assert f.preview is not None
        try:
            preview.update(f"[#ffb000]✓[/#ffb000] {f.preview(raw)}")
        except Exception as exc:  # parse helpers raise their domain errors
            preview.update(f"[red]✗ {exc}[/red]")

    @on(Input.Submitted)
    def _submitted(self) -> None:
        self.action_save()

    @on(Button.Pressed, "#save")
    def _save_pressed(self) -> None:
        self.action_save()

    @on(Button.Pressed, "#cancel")
    def _cancel_pressed(self) -> None:
        self.dismiss(None)

    def _collect(self) -> tuple[dict[str, Any] | None, str | None]:
        """(values, error). Error names the first invalid field."""
        values: dict[str, Any] = {}
        for f in self.fields:
            widget = self.query_one(f"#field-{f.name}")
            if f.kind == "toggle":
                assert isinstance(widget, Switch)
                values[f.name] = widget.value
                continue
            if f.kind == "select":
                assert isinstance(widget, Select)
                if isinstance(widget.value, type(Select.NULL)):
                    if f.required:
                        return None, f"{f.label} is required"
                    values[f.name] = None
                else:
                    values[f.name] = widget.value
                continue
            assert isinstance(widget, Input)
            raw = widget.value.strip()
            if not raw:
                if f.required:
                    widget.focus()
                    return None, f"{f.label} is required"
                values[f.name] = ""
                continue
            if f.validate is not None:
                verdict = f.validate(raw)
                if verdict is not True:
                    widget.focus()
                    message = verdict if isinstance(verdict, str) else f"Invalid {f.label.lower()}"
                    return None, message
            values[f.name] = raw
        return values, None

    def action_save(self) -> None:
        values, error = self._collect()
        if error is not None:
            self.query_one("#form-error", Static).update(f"[red]✗ {error}[/red]")
            return
        self.dismiss(values)
