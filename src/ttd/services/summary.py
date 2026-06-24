"""Dashboard-style ledger summaries (week totals, unbilled value)."""

from datetime import date, timedelta
from decimal import Decimal

from ttd.config.loader import get_settings
from ttd.core.rollup import amount as rollup_amount
from ttd.services import entries as entry_svc
from ttd.services import projects as project_svc
from ttd.storage.db import in_db_session


@in_db_session
async def week_total(today: date, week_start: str = "monday") -> int:
    """Billable and non-billable seconds logged from week start through today."""
    offset = today.weekday() if week_start == "monday" else (today.weekday() + 1) % 7
    start = today - timedelta(days=offset)
    rows = await entry_svc.list_entries(date_from=start, date_to=today)
    return sum(r.entry.seconds for r in rows)


@in_db_session
async def unbilled_totals() -> tuple[int, Decimal | None]:
    """Uninvoiced billable seconds and summed billable value (USD), or None if unrated."""
    rows = await entry_svc.list_entries()
    settings = get_settings()
    seconds = 0
    total: Decimal | None = None
    for r in rows:
        if r.entry.invoice_id is not None or not r.entry.billable:
            continue
        seconds += r.entry.seconds
        rate = await project_svc.effective_rate(r.project)
        if rate is None:
            rate = settings.business.default_hourly_rate
        value = rollup_amount(r.entry.seconds, rate)
        if value is not None:
            total = (total or Decimal("0")) + value
    return seconds, total
