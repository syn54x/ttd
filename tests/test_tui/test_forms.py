"""FormModal behavior, driven headless in a bare host app."""

from textual.app import App
from textual.widgets import Input, Select, Static, Switch

from ttd.tui.widgets.forms import FormField, FormModal


class HostApp(App):
    CSS_PATH = "../../src/ttd/tui/ttd.tcss"

    def __init__(self, modal: FormModal):
        super().__init__()
        self.modal = modal
        self.result: dict | None = "UNSET"  # type: ignore[assignment]

    async def on_mount(self) -> None:
        def _done(value: dict | None) -> None:
            self.result = value

        await self.push_screen(self.modal, _done)


def fields():
    return [
        FormField("name", "Name", required=True),
        FormField("rate", "Rate", validate=lambda t: True if t.isdigit() else "digits only"),
        FormField("kind", "Kind", kind="select", choices=[("a", "Alpha"), ("b", "Beta")]),
        FormField("active", "Active", kind="toggle", value=True),
    ]


async def test_prefill_and_submit():
    modal = FormModal("t", fields())
    app = HostApp(modal)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal.query_one("#field-name", Input).value = "Acme"
        modal.query_one("#field-rate", Input).value = "150"
        modal.query_one("#field-kind", Select).value = "b"
        modal.query_one("#field-active", Switch).value = False
        modal.action_save()
        await pilot.pause()
        assert app.result == {"name": "Acme", "rate": "150", "kind": "b", "active": False}


async def test_required_field_blocks_save():
    modal = FormModal("t", fields())
    app = HostApp(modal)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal.action_save()
        await pilot.pause()
        assert app.result == "UNSET"  # not dismissed
        assert "Name is required" in str(modal.query_one("#form-error", Static).content)


async def test_validator_failure_blocks_save():
    modal = FormModal("t", fields())
    app = HostApp(modal)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal.query_one("#field-name", Input).value = "X"
        modal.query_one("#field-rate", Input).value = "abc"
        modal.action_save()
        await pilot.pause()
        assert app.result == "UNSET"
        assert "digits only" in str(modal.query_one("#form-error", Static).content)


async def test_optional_fields_default():
    modal = FormModal("t", fields())
    app = HostApp(modal)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal.query_one("#field-name", Input).value = "X"
        modal.action_save()
        await pilot.pause()
        assert app.result["rate"] == ""
        assert app.result["kind"] is None
        assert app.result["active"] is True


async def test_escape_dismisses_none():
    modal = FormModal("t", fields())
    app = HostApp(modal)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_spec_preview_updates_live():
    from ttd.cli._pickers import describe_timespec, validate_timespec

    modal = FormModal(
        "t",
        [
            FormField(
                "time",
                "Time",
                kind="spec",
                validate=validate_timespec,
                preview=describe_timespec,
                required=True,
            )
        ],
    )
    app = HostApp(modal)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal.query_one("#field-time", Input).value = "today 09:00 to 11:30"
        await pilot.pause()
        preview = str(modal.query_one("#preview-time", Static).content)
        assert "2:30" in preview
        modal.query_one("#field-time", Input).value = "banana"
        await pilot.pause()
        assert "✗" in str(modal.query_one("#preview-time", Static).content)
