# /// script
# requires-python = ">=3.13"
# dependencies = ["ferro-orm==0.10.5"]
# ///
"""Repro: sqlx worker panics after ALTER TABLE ADD COLUMN on a live pool.

Flow (mirrors a consumer adding nullable model fields between releases):

1. A database exists with a table created by an older model (fewer columns).
2. The app connects with the *current* model (which declares the new columns),
   then applies `ALTER TABLE ... ADD COLUMN` via ferro.raw because
   auto_migrate only creates missing tables.
3. The next ORM query on that table panics in the sqlx worker thread
   ("index out of bounds") and returns no rows instead of the table data.

Run: uv run docs/upstream/ferro-alter-table-stale-pool-repro-standalone.py
"""

import asyncio
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from ferro import FerroField, connect, reset_engine
from ferro.models import Model
from ferro.raw import execute, fetch_all


# Current model: three columns (paid_date, set_aside_rate, set_aside) were
# added after the original release shipped.
class Invoice(Model):
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    number: Annotated[str, FerroField(unique=True, index=True)]
    client_id: Annotated[UUID, FerroField(index=True)]
    period_start: Annotated[date, FerroField(db_type="date")]
    period_end: Annotated[date, FerroField(db_type="date")]
    issued_date: Annotated[date, FerroField(db_type="date")]
    due_date: Annotated[date | None, FerroField(db_type="date")] = None
    currency: str = "USD"
    subtotal: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    status: str = "draft"
    notes: str = ""
    created_at: datetime
    paid_date: Annotated[date | None, FerroField(db_type="date")] = None
    set_aside_rate: Decimal | None = None
    set_aside: Decimal | None = None


# A model whose table does not exist yet, so auto_migrate has table-creation
# work to do on connect (same as the consumer flow that hit the panic).
class TaxPayment(Model):
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    year: Annotated[int, FerroField(index=True)]
    amount: Decimal = Decimal("0")


OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS "invoice" (
    "client_id" uuid_text NOT NULL,
    "created_at" timestamp_with_timezone_text NOT NULL,
    "currency" varchar(3) NOT NULL,
    "due_date" date_text,
    "id" uuid_text PRIMARY KEY,
    "issued_date" date_text NOT NULL,
    "notes" varchar NOT NULL,
    "number" varchar NOT NULL UNIQUE,
    "period_end" date_text NOT NULL,
    "period_start" date_text NOT NULL,
    "status" text NOT NULL,
    "subtotal" real NOT NULL,
    "tax" real NOT NULL,
    "tax_rate" real NOT NULL,
    "total" real NOT NULL
)
"""

NEW_COLUMNS = (
    ("paid_date", "date_text"),
    ("set_aside_rate", "real"),
    ("set_aside", "real"),
)


async def main() -> None:
    db = Path(tempfile.mkdtemp()) / "repro.db"
    dsn = f"sqlite:{db}?mode=rwc"

    # --- phase 1: simulate the old release's database -------------------------
    await connect(dsn)
    await execute(OLD_SCHEMA)
    await execute(
        'INSERT INTO "invoice" (client_id, created_at, currency, id, issued_date, notes, '
        "number, period_end, period_start, status, subtotal, tax, tax_rate, total) "
        "VALUES (?, ?, 'USD', ?, '2026-05-01', '', '2026-001', '2026-04-30', "
        "'2026-04-01', 'paid', 900.0, 0, 0, 900.0)",
        uuid4(),
        datetime.now(),
        uuid4(),
    )
    reset_engine()

    # --- phase 2: the new release connects and migrates -----------------------
    await connect(dsn, auto_migrate=True)  # creates taxpayment table

    rows = await fetch_all("PRAGMA table_info(invoice)")
    present = {row["name"] for row in rows}
    for column, ddl in NEW_COLUMNS:
        if column not in present:
            await execute(f'ALTER TABLE "invoice" ADD COLUMN "{column}" {ddl}')

    invoices = await Invoice.all()  # sqlx worker panics here on 0.10.5
    print(f"fetched {len(invoices)} invoice(s); expected 1")
    assert len(invoices) == 1, "BUG: row exists in the table but the ORM returned nothing"
    print("OK — no panic, row hydrated:", invoices[0].number, invoices[0].paid_date)


asyncio.run(main())
