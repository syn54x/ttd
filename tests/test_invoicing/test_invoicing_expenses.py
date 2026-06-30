from datetime import date
from decimal import Decimal

from ttd.config.schema import Settings
from ttd.reporting import periods
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc
from ttd.storage.models import Expense


async def _client_project(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")


def _june() -> periods.Period:
    return periods.range_period(date(2026, 6, 1), date(2026, 6, 30))


async def test_draft_includes_unbilled_expenses_untaxed(db):
    await _client_project(db)
    await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()  # tax_rate defaults to 0
    draft = await svc.build_draft("acme-corp", _june(), settings)
    assert draft.expenses_subtotal == Decimal("100")
    assert draft.subtotal == Decimal("0")  # no time entries
    assert draft.total == Decimal("100")


async def test_persist_locks_expenses_and_stores_subtotal(db):
    await _client_project(db)
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()
    draft = await svc.build_draft("acme-corp", _june(), settings)
    invoice = await svc.persist_draft(draft, settings)

    refetched = await Expense.get_or_none(exp.id)
    assert refetched.invoice_id == invoice.id  # locked
    assert invoice.expenses_subtotal == Decimal("100")
    view = await svc.get_invoice(invoice.number)
    assert len(view.expense_lines) == 1
    assert view.expense_lines[0].amount == Decimal("100")


async def test_void_releases_expenses(db):
    await _client_project(db)
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", _june(), settings), settings
    )
    await svc.mark_invoice(invoice.number, "void")
    assert (await Expense.get_or_none(exp.id)).invoice_id is None


async def test_refresh_drops_deleted_expense(db):
    await _client_project(db)
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", _june(), settings), settings
    )
    # Release + delete the expense, then refresh.
    await svc.mark_invoice(invoice.number, "void")
    # Re-invoice fresh so the expense is linked again, then delete underlying expense
    # (simulating an expense removed from the period):
    invoice2 = await svc.persist_draft(
        await svc.build_draft("acme-corp", _june(), settings), settings
    )
    locked = await Expense.get_or_none(exp.id)
    locked.invoice_id = None
    await locked.save()
    await locked.delete()
    preview = await svc.preview_refresh(invoice2.number, settings)
    fresh = await svc.apply_refresh(invoice2.number, preview, settings)
    assert fresh.expenses_subtotal == Decimal("0")
    assert fresh.total == Decimal("0")
