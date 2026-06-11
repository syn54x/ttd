"""`ttd db …` commands."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.prompt import Confirm

from ttd.cli._output import console, success
from ttd.cli._run import TtdApp, abort, with_db
from ttd.config.loader import get_settings
from ttd.storage.db import db_lifespan
from ttd.storage.models import Client, Entry, Invoice, Project

app = TtdApp(name="db", help="Database utilities.")


@app.command(name="path")
def path() -> None:
    """Show the database file location."""
    console.print(str(get_settings().db_path))


@app.command(name="backup")
def backup(
    dest: Annotated[Path | None, Parameter(help="Destination file or directory")] = None,
) -> None:
    """Copy the database to a timestamped backup."""
    src = get_settings().db_path
    if not src.is_file():
        console.print("[muted]No database yet — nothing to back up.[/muted]")
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = dest if dest is not None else src.parent
    if target.is_dir() or dest is None:
        target = target / f"ttd-{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    success(f"Backed up to {target}")


@app.command(name="migrate")
@with_db
async def migrate() -> None:
    """Create/upgrade the schema (also happens automatically on first use)."""
    success("Schema is up to date")


@app.command(name="doctor")
@with_db
async def doctor() -> None:
    """Sanity-check the database and print summary counts."""
    counts = {
        "clients": await Client.select().count(),
        "projects": await Project.select().count(),
        "entries": await Entry.select().count(),
        "invoices": await Invoice.select().count(),
    }
    console.print(f"db: {get_settings().db_path}")
    for name, n in counts.items():
        console.print(f"  {name}: {n}")
    success("Database looks healthy")


@app.command(name="seed-demo")
async def seed_demo(
    *,
    yes: Annotated[bool, Parameter(help="Skip confirmation")] = False,
    reset: Annotated[bool, Parameter(help="Delete the existing database first")] = False,
) -> None:
    """Populate demo clients, projects, and ~3 months of entries (for trying the TUI)."""
    db_path = get_settings().db_path
    prompt = (
        f"Delete {db_path} and reseed with demo data?"
        if reset
        else "Add demo data to the current database?"
    )
    if not yes and not Confirm.ask(prompt):
        abort()
    # The reset must happen before the DB opens, so the lifespan is managed
    # inline rather than via @with_db.
    if reset:
        for suffix in ("", "-wal", "-shm"):  # sqlite sidecar files too
            sidecar = Path(f"{db_path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()

    async def _seed() -> int:
        import random
        from datetime import timedelta
        from decimal import Decimal

        from ttd.services import clients as client_svc
        from ttd.services import entries as entry_svc
        from ttd.services import projects as project_svc

        random.seed(42)
        now = datetime.now()
        await client_svc.create_client(
            "Acme Corp", hourly_rate=Decimal("150"), email="billing@acme.test"
        )
        await client_svc.create_client("Beta LLC", hourly_rate=Decimal("95"), currency="EUR")
        await project_svc.create_project("API Rewrite", "acme-corp")
        await project_svc.create_project("Mobile App", "acme-corp", hourly_rate=Decimal("175"))
        await project_svc.create_project("Design System", "beta-llc")
        projects = ["api-rewrite", "api-rewrite", "mobile-app", "design-system"]
        notes = ["", "standup + pairing", "code review", "deep work", "client call"]
        count = 0
        # today always has work, so the TUI's default views aren't empty
        today = now.date().isoformat()
        await entry_svc.log_entry(
            f"{today} 09:00 for 2h30m", "api-rewrite", now=now, note="deep work", force=True
        )
        await entry_svc.log_entry(
            f"{today} 13:00 for 1h30m", "design-system", now=now, note="reviews", force=True
        )
        count += 2
        for days_back in range(1, 92):
            day = (now - timedelta(days=days_back)).date()
            if day.weekday() >= 5 or random.random() < 0.25:
                continue
            start_hour = random.choice([8, 9, 10])
            length = random.choice([2, 3, 4, 6])
            spec = f"{day.isoformat()} {start_hour:02d}:00 for {length}h"
            await entry_svc.log_entry(
                spec, random.choice(projects), now=now, note=random.choice(notes), force=True
            )
            count += 1
        return count

    async with db_lifespan():
        count = await _seed()
    success(f"Seeded 2 clients, 3 projects, {count} entries — run `ttd` to explore")
