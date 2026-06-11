from datetime import date, datetime, time
from uuid import uuid4

import pytest

from ttd.core.errors import TtdError
from ttd.interchange.importer import apply_plan, build_plan
from ttd.services import clients as client_svc
from ttd.services import entries as entry_svc
from ttd.services import projects as project_svc

NOW = datetime(2026, 6, 9, 15, 0)


def row(**overrides):
    base = {
        "uid": "",
        "client": "acme",
        "project": "api",
        "date": "2026-06-08",
        "start": "09:00:00",
        "end": "11:00:00",
        "seconds": 7200,
        "note": "",
        "tags": "",
        "billable": "true",
        "invoice_number": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
async def seeded(db):
    await client_svc.create_client("Acme")
    await project_svc.create_project("API", "acme")
    return db


async def test_new_rows_imported(seeded):
    plan = await build_plan(
        [row(), row(date="2026-06-09", start="13:00", end="14:00", seconds=3600)]
    )
    assert len(plan.new) == 2
    written = await apply_plan(plan)
    assert written == 2
    assert len(await entry_svc.list_entries()) == 2


async def test_content_match_skips_by_default(seeded):
    await apply_plan(await build_plan([row()]))
    plan = await build_plan([row()])
    assert len(plan.new) == 0
    assert plan.skip[0][1] == "already exists"


async def test_on_conflict_update(seeded):
    await apply_plan(await build_plan([row()]))
    rows = await entry_svc.list_entries()
    uid = str(rows[0].entry.id)
    plan = await build_plan([row(uid=uid, note="updated note")], on_conflict="update")
    assert len(plan.update) == 1
    await apply_plan(plan)
    rows = await entry_svc.list_entries()
    assert len(rows) == 1
    assert rows[0].entry.note == "updated note"


async def test_on_conflict_duplicate_gets_new_id(seeded):
    await apply_plan(await build_plan([row()]))
    rows = await entry_svc.list_entries()
    uid = str(rows[0].entry.id)
    plan = await build_plan([row(uid=uid)], on_conflict="duplicate")
    await apply_plan(plan)
    rows = await entry_svc.list_entries()
    assert len(rows) == 2
    assert rows[0].entry.id != rows[1].entry.id


async def test_invoiced_entries_never_touched(seeded):
    await apply_plan(await build_plan([row()]))
    rows = await entry_svc.list_entries()
    entry = rows[0].entry
    entry.invoice_id = uuid4()
    await entry.save()
    plan = await build_plan([row(uid=str(entry.id), note="sneaky")], on_conflict="update")
    assert len(plan.update) == 0
    assert plan.skip[0][1] == "matches an invoiced entry"


async def test_missing_project_requires_create_missing(seeded):
    plan = await build_plan([row(project="unknown")])
    assert plan.missing_projects == {("acme", "unknown")}
    with pytest.raises(TtdError, match="--create-missing"):
        await apply_plan(plan)
    written = await apply_plan(plan, create_missing=True)
    assert written == 1
    project = await project_svc.get_project("unknown", "acme")
    assert project.name == "Unknown"


async def test_row_errors_collected_not_fatal(seeded):
    plan = await build_plan([row(), row(date="not-a-date"), row(seconds="", hours="")])
    assert len(plan.new) == 1
    assert len(plan.errors) == 2
    assert plan.errors[0][0] == 3  # 1-header, row 3 is the second data row


async def test_duplicate_rows_within_file(seeded):
    plan = await build_plan([row(), row()])
    assert len(plan.new) == 1
    assert plan.skip[0][1] == "duplicate row within file"


async def test_default_client_project_fill(seeded):
    plan = await build_plan(
        [row(client="", project="")], default_client="acme", default_project="api"
    )
    assert len(plan.new) == 1
    assert plan.new[0].client == "acme"


async def test_hours_fallback_when_no_seconds(seeded):
    plan = await build_plan([row(seconds="", hours="2.5", start="", end="")])
    assert len(plan.new) == 1
    assert plan.new[0].seconds == 9000


async def test_imported_interval_entry_times(seeded):
    await apply_plan(await build_plan([row()]))
    entry = (await entry_svc.list_entries())[0].entry
    assert entry.work_date == date(2026, 6, 8)
    assert entry.started_at.time() == time(9, 0)
    assert entry.ended_at.time() == time(11, 0)
