"""Generate the docs TUI screenshots (SVG) against a seeded sandbox database.

Drives the Textual app headless and exports one SVG per documented screen
state into docs/pages/assets/screenshots/. The sandbox is a temp directory
(TTD_DB_PATH + TTD_CONFIG_DIR), so a real ledger is never touched. Output
depends on the current date (seed data is date-relative), so screenshots are
regenerated manually via `just docs-shots` and committed.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from seed_docs_demo import seed_sandbox  # sibling script, importable when run from scripts/

OUT_DIR = Path(__file__).parent.parent / "docs" / "pages" / "assets" / "screenshots"
SIZE = (100, 32)

QUICKLOG_KEYS = {" ": "space", "-": "minus", ":": "colon"}


async def _shot(name: str, keys: list[str], *, settle: int = 4) -> None:
    from ttd.tui.app import TtdApp

    app = TtdApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        for _ in range(settle):
            await pilot.pause()
        svg = app.export_screenshot(title="ttd")
        # keep the committed artifact stable under the trailing-whitespace hook
        svg = "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
        (OUT_DIR / f"{name}.svg").write_text(svg)
    print(f"  {name}.svg")


async def _generate() -> None:
    from ttd.services import timer as timer_svc
    from ttd.storage.db import close_db, init_db

    await _shot("dashboard", [])
    await _shot("timesheet-week", ["2", "w"])
    await _shot("clients-tree", ["3"])
    await _shot("reports-month", ["4", "m"])
    await _shot("invoices-list", ["5"])
    await _shot("taxes", ["6"])
    await _shot("quicklog", ["l", *[QUICKLOG_KEYS.get(c, c) for c in "yesterday 9-11:30"]])

    os.environ["TTD_DISPLAY__THEME"] = "ttd-light"
    await _shot("dashboard-light", [])
    del os.environ["TTD_DISPLAY__THEME"]

    now = datetime.now()
    await init_db()
    try:
        await timer_svc.start_timer("api-rewrite", now=now, at=now - timedelta(minutes=85))
    finally:
        await close_db()
    await _shot("dashboard-timer", [])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name in [k for k in os.environ if k.startswith("TTD_")]:
            del os.environ[name]
        os.environ["TTD_DB_PATH"] = str(Path(tmp) / "demo.db")
        os.environ["TTD_CONFIG_DIR"] = str(Path(tmp) / "config")
        seed_sandbox()
        asyncio.run(_generate())
    print(f"✓ screenshots written to {OUT_DIR}")


if __name__ == "__main__":
    main()
