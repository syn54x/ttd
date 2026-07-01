from datetime import date, datetime
from decimal import Decimal

from ttd.config.schema import Settings
from ttd.reporting import periods
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc
from ttd.storage.models import Expense


async def _setup(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")


def _june() -> periods.Period:
    return periods.range_period(date(2026, 6, 1), date(2026, 6, 30))


async def test_invoice_period_tightens_to_billed_entries(db):
    await _setup(db)
    from ttd.services import entries as entry_svc

    await entry_svc.log_entry("2026-06-16 9am-11am", "api-rewrite", now=datetime(2026, 6, 16, 12))
    await entry_svc.log_entry("2026-06-20 9am-10am", "api-rewrite", now=datetime(2026, 6, 20, 12))
    settings = Settings()
    draft = await svc.build_draft("acme-corp", _june(), settings)
    invoice = await svc.persist_draft(draft, settings)
    assert invoice.period_start == date(2026, 6, 16)  # not June 1
    assert invoice.period_end == date(2026, 6, 20)  # not June 30


async def test_invoice_period_from_expenses_only(db):
    await _setup(db)
    await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 18)
    )
    settings = Settings()
    draft = await svc.build_draft("acme-corp", _june(), settings)
    invoice = await svc.persist_draft(draft, settings)
    assert invoice.period_start == date(2026, 6, 18)
    assert invoice.period_end == date(2026, 6, 18)


async def test_invoice_period_spans_time_and_expenses(db):
    await _setup(db)
    from ttd.services import entries as entry_svc

    await entry_svc.log_entry("2026-06-16 9am-11am", "api-rewrite", now=datetime(2026, 6, 16, 12))
    await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 25)
    )
    settings = Settings()
    draft = await svc.build_draft("acme-corp", _june(), settings)
    invoice = await svc.persist_draft(draft, settings)
    assert invoice.period_start == date(2026, 6, 16)
    assert invoice.period_end == date(2026, 6, 25)


async def test_refresh_reduces_period_when_item_removed(db):
    await _setup(db)
    from ttd.services import entries as entry_svc

    await entry_svc.log_entry("2026-06-16 9am-11am", "api-rewrite", now=datetime(2026, 6, 16, 12))
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 25)
    )
    settings = Settings()
    draft = await svc.build_draft("acme-corp", _june(), settings)
    invoice = await svc.persist_draft(draft, settings)
    assert invoice.period_end == date(2026, 6, 25)
    # release + delete the later expense, then refresh
    locked = await Expense.get_or_none(exp.id)
    locked.invoice_id = None
    await locked.save()
    await locked.delete()
    preview = await svc.preview_refresh(invoice.number, settings)
    refreshed = await svc.apply_refresh(invoice.number, preview, settings)
    assert refreshed.period_end == date(2026, 6, 16)  # period tightened back to the entry
