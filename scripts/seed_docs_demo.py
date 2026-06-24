"""Seed the docs demo sandbox: demo data plus invoices and a tax payment.

Operates on whatever database TTD_DB_PATH points at (callers must set it —
this refuses to run against the default real ledger). Writes a small sandbox
config (rate, identity, set-aside) into TTD_CONFIG_DIR. Used by
scripts/gen_screenshots.py and `just docs-gifs` so every documented surface
has data on it.
"""

import asyncio
import os
import subprocess
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

SANDBOX_CONFIG = """\
[user]
name = "Alice Developer"
email = "alice@example.com"

[business]
default_hourly_rate = 150

[tax]
set_aside_rate = 0.30
"""


def _month_period(anchor: date):
    from ttd.reporting.periods import Period

    start = anchor.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    end = next_month - timedelta(days=1)
    return Period(start=start, end=end, label=start.strftime("%B %Y"))


async def seed_invoices_and_taxes() -> None:
    """Demo invoices in three states plus a recorded IRS payment."""
    from ttd.config.loader import get_settings
    from ttd.core.taxes import TaxQuarter
    from ttd.services import invoicing, taxes
    from ttd.storage.db import db_lifespan

    settings = get_settings()
    async with db_lifespan(settings):
        today = date.today()
        for months_back, (status, paid_offset) in enumerate(
            [("sent", None), ("paid", 10), ("paid", 40)], start=1
        ):
            anchor = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            for _ in range(months_back - 1):
                anchor = (anchor - timedelta(days=1)).replace(day=1)
            draft = await invoicing.build_draft("acme-corp", _month_period(anchor), settings)
            if not draft.lines:
                continue
            invoice = await invoicing.persist_draft(draft, settings)
            await invoicing.mark_invoice(invoice.number, "sent")
            if status == "paid":
                await invoicing.mark_invoice(
                    invoice.number,
                    "paid",
                    paid_date=today - timedelta(days=paid_offset or 0),
                    set_aside_rate=settings.tax.set_aside_rate,
                )
        await taxes.record_payment(
            TaxQuarter.from_date(today - timedelta(days=40)),
            Decimal("1200"),
            paid_on=today - timedelta(days=30),
            note="EFTPS",
        )


def seed_sandbox() -> None:
    """Write the sandbox config, seed demo data, then add invoices/taxes."""
    if "TTD_DB_PATH" not in os.environ or "TTD_CONFIG_DIR" not in os.environ:
        print("Refusing to seed: set TTD_DB_PATH and TTD_CONFIG_DIR to sandbox paths first.")
        raise SystemExit(1)
    config_dir = Path(os.environ["TTD_CONFIG_DIR"])
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(SANDBOX_CONFIG)
    subprocess.run(
        ["uv", "run", "ttd", "db", "seed-demo", "--yes"],
        check=True,
        capture_output=True,
    )
    asyncio.run(seed_invoices_and_taxes())


def main() -> None:
    seed_sandbox()
    print(f"✓ docs demo sandbox seeded at {os.environ['TTD_DB_PATH']}")


if __name__ == "__main__":
    main()
