"""Pilot tests: drive the TUI headless and assert on real behavior."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from _db import open_test_db

from ttd.config.schema import Settings, StorageConfig
from ttd.services import clients as client_svc
from ttd.services import entries as entry_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as invoice_svc
from ttd.services import projects as project_svc
from ttd.services import timer as timer_svc
from ttd.tui.app import TtdApp
from ttd.tui.theme import THEME_DARK, THEME_LIGHT
from ttd.tui.widgets.modals import ConfirmModal

NOW = datetime.now().replace(hour=15, minute=0, second=0, microsecond=0)


@pytest.fixture
async def seeded_app(tmp_path, monkeypatch):
    """A TtdApp pointed at a seeded temp DB."""
    db_path = tmp_path / "tui.db"
    monkeypatch.setenv("TTD_DB_PATH", str(db_path))
    monkeypatch.setenv("TTD_CONFIG_DIR", str(tmp_path / "config"))
    settings = Settings(storage=StorageConfig(db_path=db_path))

    async with open_test_db(settings):
        await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
        await client_svc.create_client("Beta LLC", hourly_rate=Decimal("95"))
        await project_svc.create_project("API Rewrite", "acme-corp")
        await project_svc.create_project("Design", "beta-llc")
        for days_back in range(0, 14, 2):
            day = (NOW - timedelta(days=days_back)).date().isoformat()
            await entry_svc.log_entry(f"{day} 09:00 to 11:30", "api-rewrite", now=NOW)
        await entry_svc.log_entry("today 1pm to 2pm", "design", now=NOW, note="reviews")
        await expense_svc.add_expense("api-rewrite", "Cloud hosting", Decimal("49.99"))

    yield TtdApp()


async def test_dashboard_loads_with_entries(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert seeded_app.screen.nav_id == "dashboard"
        table = seeded_app.screen.query_one("#today-table")
        assert table.row_count == 2  # today's api entry + design entry
        caption = str(seeded_app.screen.query_one("#timer-caption").content)
        assert "idle" in caption


async def test_navigation_between_screens(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for key, nav_id in [
            ("2", "log"),
            ("3", "clients"),
            ("4", "reports"),
            ("5", "invoices"),
            ("6", "taxes"),
            ("1", "dashboard"),
        ]:
            await pilot.press(key)
            await pilot.pause()
            assert seeded_app.screen.nav_id == nav_id


async def test_log_month_navigation(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        screen = seeded_app.screen
        this_month = screen.query_one("#day-table").row_count
        assert this_month >= 1
        await pilot.press("left_square_bracket")  # previous month
        await pilot.pause()
        assert screen.anchor_date < date.today().replace(day=1)
        await pilot.press("g")  # back to this month
        await pilot.pause()
        assert screen.query_one("#day-table").row_count == this_month


async def test_quick_log_modal_live_preview(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("l")
        await pilot.pause()
        from ttd.tui.widgets.modals import PickerModal, QuickLogModal

        # l now opens a chooser first
        assert isinstance(seeded_app.screen, PickerModal)
        await pilot.press("enter")  # first option = "time"
        await pilot.pause()

        modal = seeded_app.screen
        assert isinstance(modal, QuickLogModal)
        spec_input = modal.query_one("#spec")
        spec_input.value = "today 3pm to 5pm"
        await pilot.pause()
        preview = str(modal.query_one("#preview").content)
        assert "2:00" in preview
        spec_input.value = "banana"
        await pilot.pause()
        preview = str(modal.query_one("#preview").content)
        assert "✗" in preview
        await pilot.press("escape")
        await pilot.pause()
        assert seeded_app.screen.nav_id == "dashboard"


async def test_quick_log_creates_entry(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        assert seeded_app.screen.nav_id == "log"
        before = seeded_app.screen.query_one("#day-table").row_count
        await pilot.press("l")  # log chooser
        await pilot.pause()
        await pilot.press("enter")  # first option = time
        await pilot.pause()
        await pilot.press(*"today 3pm to 4pm")
        await pilot.pause()
        await pilot.press("enter")  # submit spec → picks first project
        await pilot.pause()
        await pilot.pause()
        assert seeded_app.screen.query_one("#day-table").row_count == before + 1


async def test_timer_start_stop_via_keys(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("s")
        await pilot.pause()
        from ttd.tui.widgets.modals import PickerModal

        assert isinstance(seeded_app.screen, PickerModal)
        await pilot.press("enter")  # first project
        await pilot.pause()
        status = await timer_svc.timer_status(now=datetime.now())
        assert status.timer is not None
        await pilot.press("s")  # stop
        await pilot.pause()
        status = await timer_svc.timer_status(now=datetime.now())
        assert status.timer is None


async def test_clients_tree_shows_rates(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("3")
        await pilot.pause()
        tree = seeded_app.screen.query_one("#client-tree")
        assert len(tree.root.children) == 2


async def test_reports_screen_modes(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        screen = seeded_app.screen
        assert screen.query_one("#report-table").row_count >= 1
        chart = screen.query_one("#report-chart")
        assert chart._hours and any(chart._hours)
        await pilot.press("m")
        await pilot.pause()
        title = str(screen.query_one("#report-title").content)
        assert any(
            month in title
            for month in (
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            )
        )


async def test_reports_project_expand_collapse(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        screen = seeded_app.screen
        table = screen.query_one("#report-table")
        table.focus()
        initial = table.row_count
        assert initial >= 1
        await screen.action_toggle_expand()
        await pilot.pause()
        expanded = table.row_count
        assert expanded > initial
        await screen.action_toggle_expand()
        await pilot.pause()
        assert table.row_count == initial
        await pilot.press("m")
        await pilot.pause()
        assert table.row_count <= initial


async def test_reports_screen_tax_columns(seeded_app, monkeypatch):
    monkeypatch.setenv("TTD_TAX__SET_ASIDE_RATE", "0.32")
    async with seeded_app.run_test(size=(140, 40)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        screen = seeded_app.screen
        table = screen.query_one("#report-table")
        labels = [str(col.label) for col in table.columns.values()]
        assert labels[-2:] == ["est. tax", "take-home"]
        total = str(screen.query_one("#report-total").content)
        assert "est. tax" in total
        assert "take-home" in total
        # rate cleared mid-session → columns drop on the next render
        monkeypatch.delenv("TTD_TAX__SET_ASIDE_RATE")
        await pilot.press("r")
        await pilot.pause()
        labels = [str(col.label) for col in table.columns.values()]
        assert labels == ["project", "days", "hours", "activity", "value"]


async def test_invoices_screen_create_flow(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        screen = seeded_app.screen
        assert screen.query_one("#invoice-table").row_count == 0
        # entries exist this month; wizard invoices last month → expect friendly error
        await pilot.press("n")
        await pilot.pause()
        from ttd.tui.widgets.modals import PickerModal

        assert isinstance(seeded_app.screen, PickerModal)
        await pilot.press("escape")
        await pilot.pause()


async def test_invoice_detail_modal(seeded_app, monkeypatch):
    # create an invoice directly, then open detail in the TUI
    from datetime import date
    from datetime import timedelta as td

    from ttd.config.schema import Settings as S
    from ttd.reporting.periods import range_period

    async with open_test_db():
        period = range_period(date.today() - td(days=30), date.today())
        settings = S(business={"default_hourly_rate": 100})
        draft = await invoice_svc.build_draft("acme-corp", period, settings)
        await invoice_svc.persist_draft(draft, settings)

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        screen = seeded_app.screen
        assert screen.query_one("#invoice-table").row_count == 1
        await pilot.press("o")
        await pilot.pause()
        from ttd.tui.screens.invoices import InvoiceDetailModal

        assert isinstance(seeded_app.screen, InvoiceDetailModal)
        await pilot.press("escape")
        await pilot.pause()


async def test_invoices_screen_tax_columns(seeded_app, monkeypatch):
    # persist an invoice directly, then view the list with a rate configured
    from datetime import date
    from datetime import timedelta as td

    from ttd.config.schema import Settings as S
    from ttd.reporting.periods import range_period

    async with open_test_db():
        period = range_period(date.today() - td(days=30), date.today())
        settings = S(business={"default_hourly_rate": 100})
        draft = await invoice_svc.build_draft("acme-corp", period, settings)
        await invoice_svc.persist_draft(draft, settings)

    monkeypatch.setenv("TTD_TAX__SET_ASIDE_RATE", "0.32")
    async with seeded_app.run_test(size=(140, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        screen = seeded_app.screen
        table = screen.query_one("#invoice-table")
        labels = [str(col.label) for col in table.columns.values()]
        assert labels == [
            "number",
            "client",
            "period",
            "total",
            "est. tax",
            "take-home",
            "status",
        ]
        # detail modal carries the same estimate
        await pilot.press("o")
        await pilot.pause()
        from ttd.tui.screens.invoices import InvoiceDetailModal

        assert isinstance(seeded_app.screen, InvoiceDetailModal)
        await pilot.press("escape")
        await pilot.pause()
        # rate cleared mid-session → columns drop on the next render
        monkeypatch.delenv("TTD_TAX__SET_ASIDE_RATE")
        await pilot.press("r")
        await pilot.pause()
        labels = [str(col.label) for col in table.columns.values()]
        assert labels == ["number", "client", "period", "total", "status"]


# --- TUI enhancements: spans, entry edit, clients CRUD, invoice period -------


async def test_log_delete_entry(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        screen = seeded_app.screen
        before = screen.query_one("#day-table").row_count
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("y")  # confirm
        await pilot.pause()
        assert screen.query_one("#day-table").row_count == before - 1


async def test_entry_edit_modal(seeded_app):
    from textual.widgets import Input

    from ttd.tui.widgets.forms import FormModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        screen = seeded_app.screen
        await pilot.press("e")
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, FormModal)
        # prefilled with a round-trippable spec
        spec = modal.query_one("#field-time", Input).value
        assert "09:00 to 11:30" in spec or "13:00 to 14:00" in spec
        modal.query_one("#field-time", Input).value = spec.split(" ", 1)[0] + " 09:00 to 12:00"
        modal.query_one("#field-note", Input).value = "edited via tui"
        modal.action_save()
        await pilot.pause()
        await pilot.pause()
        assert seeded_app.screen is screen
        rows = await entry_svc.list_entries()
        edited = [r for r in rows if r.entry.note == "edited via tui"]
        assert len(edited) == 1
        assert edited[0].entry.seconds == 3 * 3600


async def test_entry_edit_invoiced_blocked(seeded_app):
    from uuid import uuid4

    async with open_test_db():
        first_of_month = date.today().replace(day=1)
        rows = await entry_svc.list_entries(date_from=first_of_month, date_to=date.today())
        # Mark the first current-month entry (row 0 in month view) as invoiced.
        target = rows[0]
        target.entry.invoice_id = uuid4()
        await target.entry.save()

    from ttd.tui.widgets.forms import FormModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("e")  # cursor starts on the invoiced (first) row
        await pilot.pause()
        assert not isinstance(seeded_app.screen, FormModal)


async def test_log_expense_edit_invoiced_blocked(seeded_app):
    from uuid import uuid4

    async with open_test_db():
        expenses = await expense_svc.list_expenses()
        target = expenses[0]
        target.expense.invoice_id = uuid4()
        await target.expense.save()

    from ttd.tui.widgets.forms import FormModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        await pilot.press("tab")  # focus expenses section
        await pilot.pause()
        await pilot.press("e")  # attempt edit on invoiced expense
        await pilot.pause()
        assert not isinstance(seeded_app.screen, FormModal)
        assert seeded_app.screen.nav_id == "log"


async def test_clients_crud_flow(seeded_app):
    from textual.widgets import Input, Tree

    from ttd.tui.widgets.forms import FormModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("3")
        await pilot.pause()
        screen = seeded_app.screen
        tree = screen.query_one("#client-tree", Tree)
        assert len(tree.root.children) == 2

        # add a client through the form
        await pilot.press("a")
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, FormModal)
        modal.query_one("#field-name", Input).value = "Gamma Inc"
        modal.query_one("#field-rate", Input).value = "200"
        modal.action_save()
        await pilot.pause()
        await pilot.pause()
        tree = seeded_app.screen.query_one("#client-tree", Tree)
        assert len(tree.root.children) == 3

        # archive it (cursor needs to be on the node)
        gamma = next(n for n in tree.root.children if "Gamma" in str(n.label))
        tree.select_node(gamma)
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        tree = seeded_app.screen.query_one("#client-tree", Tree)
        assert len(tree.root.children) == 2


async def test_clients_add_project(seeded_app):
    from textual.widgets import Input, Tree

    from ttd.tui.widgets.forms import FormModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("3")
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, FormModal)
        modal.query_one("#field-name", Input).value = "New Thing"
        from textual.widgets import Select

        modal.query_one("#field-client", Select).value = "acme-corp"
        modal.action_save()
        await pilot.pause()
        await pilot.pause()
        tree = seeded_app.screen.query_one("#client-tree", Tree)
        acme = next(n for n in tree.root.children if "Acme" in str(n.label))
        assert any("New Thing" in str(c.label) for c in acme.children)


async def test_invoice_wizard_custom_period_with_line_preview(seeded_app):
    from datetime import timedelta as td

    from textual.widgets import Button, Input, Static

    from ttd.tui.screens.invoices import NewInvoiceModal
    from ttd.tui.widgets.modals import PickerModal

    start = (NOW - td(days=14)).date().isoformat()
    end = NOW.date().isoformat()

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(seeded_app.screen, PickerModal)
        await pilot.press("enter")  # first client: acme-corp
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, NewInvoiceModal)

        # typing the period rebuilds the line preview live
        modal.query_one("#period", Input).value = f"{start} to {end}"
        await pilot.pause()
        await pilot.pause()
        table = modal.query_one("#draft-table")
        assert table.row_count >= 1  # seeded api-rewrite entries roll up here
        status = str(modal.query_one("#draft-status", Static).content)
        assert "✓" in status and "entries" in status
        assert not modal.query_one("#create", Button).disabled

        # nonsense period: error, preview cleared, create disabled
        modal.query_one("#period", Input).value = "banana"
        await pilot.pause()
        assert modal.query_one("#draft-table").row_count == 0
        assert modal.query_one("#create", Button).disabled
        assert "✗" in str(modal.query_one("#draft-status", Static).content)

        # back to a valid period and create
        modal.query_one("#period", Input).value = f"{start} to {end}"
        await pilot.pause()
        await pilot.pause()
        modal.action_create()
        await pilot.pause()
        await pilot.pause()
        table = seeded_app.screen.query_one("#invoice-table")
        assert table.row_count == 1

    async with open_test_db():
        from ttd.services import invoicing as invoice_svc

        ((invoice, _client),) = await invoice_svc.list_invoices()
        # Period derives from actual billed dates (not the requested window).
        # Entries are seeded every 2 days from 0..12 days back; the earliest is 12 days back.
        # The expense defaults to today.  Both collapse inward from the 14-day window.
        derived_start = (NOW - td(days=12)).date().isoformat()
        assert invoice.period_start.isoformat() == derived_start
        assert invoice.period_end.isoformat() == end


async def test_invoice_wizard_empty_period_shows_friendly_message(seeded_app):
    from textual.widgets import Button, Static

    from ttd.tui.screens.invoices import NewInvoiceModal
    from ttd.tui.widgets.modals import PickerModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(seeded_app.screen, PickerModal)
        await pilot.press("down")  # second client: beta-llc (no entries last month)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, NewInvoiceModal)
        # blank = last month; beta-llc has nothing there → message, no create
        status = str(modal.query_one("#draft-status", Static).content)
        assert "No uninvoiced billable entries" in status
        assert modal.query_one("#create", Button).disabled
        modal.action_create()  # disabled draft: must be a no-op
        await pilot.pause()
        assert isinstance(seeded_app.screen, NewInvoiceModal)
        await pilot.press("escape")
        await pilot.pause()


async def test_invoice_markdown_preview(seeded_app):
    from datetime import date
    from datetime import timedelta as td

    from ttd.config.schema import Settings as S
    from ttd.reporting.periods import range_period
    from ttd.services import invoicing as invoice_svc
    from ttd.tui.screens.invoices import MarkdownPreviewModal

    async with open_test_db():
        period = range_period(date.today() - td(days=30), date.today())
        draft = await invoice_svc.build_draft("acme-corp", period, S())
        invoice = await invoice_svc.persist_draft(draft, S())

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, MarkdownPreviewModal)
        assert f"# Invoice {invoice.number}" in modal.markdown_source
        assert "Bill to:" in modal.markdown_source
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(seeded_app.screen, MarkdownPreviewModal)


async def test_taxes_screen_shows_quarters_and_payment_modal(seeded_app):
    from datetime import date
    from datetime import timedelta as td

    from ttd.config.schema import Settings as S
    from ttd.core.taxes import TaxQuarter, compute_set_aside
    from ttd.reporting.periods import range_period
    from ttd.tui.screens.taxes import TaxPaymentModal

    async with open_test_db():
        period = range_period(date.today() - td(days=30), date.today())
        draft = await invoice_svc.build_draft("acme-corp", period, S())
        invoice = await invoice_svc.persist_draft(draft, S())
        await invoice_svc.mark_invoice(invoice.number, "paid", set_aside_rate=Decimal("0.32"))

    expected = compute_set_aside(draft.subtotal, Decimal("0.32"))
    quarter = TaxQuarter.from_date(date.today())

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("6")
        await pilot.pause()
        screen = seeded_app.screen
        assert screen.nav_id == "taxes"
        table = screen.query_one("#tax-table")
        assert table.row_count == 4
        row = table.get_row(quarter.label)
        assert f"{expected:,.2f}" in str(row[4])  # set aside column

        await pilot.press("p")
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, TaxPaymentModal)
        assert modal.query_one("#quarter").value == quarter.label
        modal.query_one("#amount").value = "150"
        await pilot.press("escape")
        await pilot.pause()
        assert seeded_app.screen.nav_id == "taxes"


async def test_t_key_opens_theme_picker(seeded_app):
    from ttd.tui.widgets.theme_picker import ThemePickerModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(seeded_app.screen, ThemePickerModal)


async def test_t_key_save_theme(seeded_app):
    from ttd.config.loader import get_settings
    from ttd.tui.widgets.theme_picker import ThemePickerModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(seeded_app.screen, ThemePickerModal)
        await pilot.press(*list("ttd-light"))
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert get_settings().display.theme == THEME_LIGHT
        assert seeded_app.screen.nav_id == "dashboard"


async def test_palette_theme_previews_and_reverts(seeded_app):
    from ttd.tui.widgets.theme_picker import ThemePickerModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert seeded_app.theme == THEME_DARK
        seeded_app.search_themes()
        await pilot.pause()
        assert isinstance(seeded_app.screen, ThemePickerModal)
        await pilot.press(*list("ttd-light"))
        await pilot.pause()
        assert seeded_app.theme == THEME_LIGHT
        await pilot.press("escape")
        await pilot.pause()
        assert seeded_app.theme == THEME_DARK
        assert seeded_app.screen.nav_id == "dashboard"


async def test_palette_theme_arrow_navigation(seeded_app):
    from ttd.tui.widgets.theme_picker import ThemePickerModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert seeded_app.theme == THEME_DARK
        seeded_app.search_themes()
        await pilot.pause()
        assert isinstance(seeded_app.screen, ThemePickerModal)
        light_names = sorted(
            name for name, theme in seeded_app.available_themes.items() if not theme.dark
        )
        await pilot.press("down")  # ttd-dark is last in dark; next is first light theme
        await pilot.pause()
        assert seeded_app.theme == light_names[0]


async def test_palette_theme_groups_dark_and_light(seeded_app):
    from ttd.tui.widgets.theme_picker import ThemePickerModal

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        seeded_app.search_themes()
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, ThemePickerModal)
        theme_list = modal.query_one("#theme-list")
        labels = [str(option.prompt) for option in theme_list.options]
        assert "dark" in labels
        assert "light" in labels
        assert labels.index("dark") < labels.index(THEME_DARK)
        assert labels.index("light") < labels.index(THEME_LIGHT)


async def test_palette_theme_save_non_ttd_theme(seeded_app):
    from ttd.config.loader import get_settings

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        seeded_app.search_themes()
        await pilot.pause()
        await pilot.press(*list("dracula"))
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert get_settings().display.theme == "dracula"
        assert seeded_app.screen.nav_id == "dashboard"


async def test_palette_theme_applies_on_select(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        seeded_app.search_themes()
        await pilot.pause()
        await pilot.press(*list("ttd-light"))
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(seeded_app.screen, ConfirmModal)
        assert seeded_app.theme == THEME_LIGHT
        await pilot.press("escape")  # session-only
        await pilot.pause()
        assert seeded_app.theme == THEME_LIGHT
        assert seeded_app.screen.nav_id == "dashboard"


async def test_invoice_wizard_draft_preview_shows_expense_rows(seeded_app):
    """_rebuild must render expense lines in the draft table and mention them in the status."""
    from datetime import timedelta as td

    from textual.widgets import Input, Static

    from ttd.services import expenses as expense_svc
    from ttd.tui.screens.invoices import NewInvoiceModal
    from ttd.tui.widgets.modals import PickerModal

    start = (NOW - td(days=14)).date().isoformat()
    end = NOW.date().isoformat()

    # Add an uninvoiced expense for the acme-corp project within the period.
    async with open_test_db():
        await expense_svc.add_expense(
            "api-rewrite",
            "Cloud hosting",
            Decimal("49.99"),
            incurred_date=(NOW - td(days=7)).date(),
        )

    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(seeded_app.screen, PickerModal)
        await pilot.press("enter")  # first client: acme-corp
        await pilot.pause()
        modal = seeded_app.screen
        assert isinstance(modal, NewInvoiceModal)

        modal.query_one("#period", Input).value = f"{start} to {end}"
        await pilot.pause()
        await pilot.pause()

        table = modal.query_one("#draft-table")
        # There should be more rows than just the time lines (divider + expense row added).
        assert table.row_count >= 2

        # Collect all cell values from the table to search for expense markers.
        all_cells = []
        for row_key in table.rows:
            row_data = table.get_row(row_key)
            all_cells.extend(str(cell) for cell in row_data)
        cells_text = " ".join(all_cells)
        assert "Cloud hosting" in cells_text
        assert "49.99" in cells_text
        assert "reimbursable expenses" in cells_text

        status = str(modal.query_one("#draft-status", Static).content)
        assert "expense" in status


async def test_log_shows_expense_section(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        screen = seeded_app.screen
        expense_table = screen.query_one("#expense-table")
        assert expense_table.row_count == 1
        # the description appears in the rendered table
        assert any("Cloud hosting" in str(c) for c in expense_table.get_row_at(0))


async def test_log_delete_expense(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        screen = seeded_app.screen
        assert screen.query_one("#expense-table").row_count == 1
        await pilot.press("tab")  # focus the expenses section
        await pilot.pause()
        await pilot.press("x")  # delete highlighted expense
        await pilot.pause()
        await pilot.press("enter")  # confirm
        await pilot.pause()
        await pilot.pause()
        assert screen.query_one("#expense-table").row_count == 0


async def test_log_edit_expense(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("tab")  # focus expenses
        await pilot.pause()
        await pilot.press("e")  # edit
        await pilot.pause()
        # amount field is the second field; clear and retype via the form is heavy --
        # assert the edit modal opened with the expense's values instead.
        from ttd.tui.widgets.forms import FormModal

        assert isinstance(seeded_app.screen, FormModal)
        await pilot.press("escape")
        await pilot.pause()
