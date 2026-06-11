from datetime import date, datetime, timedelta

import pytest

from ttd.core.errors import ConflictError, InvoicedEntryError, NotFoundError
from ttd.services import clients as client_svc
from ttd.services import entries as entry_svc
from ttd.services import projects as project_svc
from ttd.services import timer as timer_svc

NOW = datetime(2026, 6, 9, 15, 0)


@pytest.fixture
async def project(db):
    await client_svc.create_client("Acme")
    return await project_svc.create_project("API", "acme")


async def test_timer_start_stop_creates_entry(project):
    await timer_svc.start_timer("api", now=NOW - timedelta(hours=2))
    entry = await timer_svc.stop_timer(now=NOW)
    assert entry.seconds == 2 * 3600
    assert entry.work_date == NOW.date()
    assert entry.started_at == NOW - timedelta(hours=2)
    status = await timer_svc.timer_status(now=NOW)
    assert status.timer is None
    assert status.today_seconds == 2 * 3600


async def test_timer_double_start_refused(project):
    await timer_svc.start_timer("api", now=NOW)
    with pytest.raises(ConflictError, match="already running"):
        await timer_svc.start_timer("api", now=NOW)


async def test_timer_stop_without_start(project):
    with pytest.raises(ConflictError, match="No timer"):
        await timer_svc.stop_timer(now=NOW)


async def test_timer_cancel_discards(project):
    await timer_svc.start_timer("api", now=NOW)
    await timer_svc.cancel_timer()
    assert (await timer_svc.timer_status(now=NOW)).timer is None
    assert await entry_svc.list_entries() == []


async def test_timer_status_elapsed(project):
    await timer_svc.start_timer("api", now=NOW - timedelta(minutes=30), note="deep work")
    status = await timer_svc.timer_status(now=NOW)
    assert status.elapsed_seconds == 30 * 60
    assert status.today_seconds == 30 * 60
    assert status.project.slug == "api"


async def test_timer_stop_before_start_rejected(project):
    await timer_svc.start_timer("api", now=NOW)
    with pytest.raises(Exception, match="before the timer started"):
        await timer_svc.stop_timer(now=NOW, at=NOW - timedelta(hours=1))


async def test_log_entry_interval(project):
    entry = await entry_svc.log_entry("today 8am to 5pm", "api", now=NOW)
    assert entry.work_date == date(2026, 6, 9)
    assert entry.seconds == 9 * 3600


async def test_log_overlap_detected_and_forced(project):
    await entry_svc.log_entry("today 9am to 11am", "api", now=NOW)
    with pytest.raises(entry_svc.OverlapError, match="Overlaps 1 existing"):
        await entry_svc.log_entry("today 10am to 12pm", "api", now=NOW)
    entry = await entry_svc.log_entry("today 10am to 12pm", "api", now=NOW, force=True)
    assert entry.seconds == 2 * 3600


async def test_duration_entries_never_overlap(project):
    await entry_svc.log_entry("today 9am to 5pm", "api", now=NOW)
    entry = await entry_svc.log_entry("2h", "api", now=NOW)  # duration-only: no clash
    assert entry.started_at is None


async def test_multiple_entries_same_day(project):
    await entry_svc.log_entry("today 8am to 10am", "api", now=NOW)
    await entry_svc.log_entry("today 10am to 12pm", "api", now=NOW)
    await entry_svc.log_entry("1h", "api", now=NOW)
    rows = await entry_svc.list_entries()
    assert len(rows) == 3
    assert sum(r.entry.seconds for r in rows) == 5 * 3600


async def test_find_entry_by_prefix(project):
    entry = await entry_svc.log_entry("1h", "api", now=NOW)
    found = await entry_svc.find_entry(str(entry.id)[:8])
    assert found.id == entry.id
    with pytest.raises(NotFoundError):
        await entry_svc.find_entry("ffffffff")


async def test_edit_entry_time_and_note(project):
    entry = await entry_svc.log_entry("1h", "api", now=NOW)
    edited = await entry_svc.edit_entry(
        str(entry.id)[:8], now=NOW, spec="today 9-11:30", note="standup"
    )
    assert edited.seconds == int(2.5 * 3600)
    assert edited.note == "standup"


async def test_invoiced_entry_locked(project):
    from uuid import uuid4

    entry = await entry_svc.log_entry("1h", "api", now=NOW)
    entry.invoice_id = uuid4()
    await entry.save()
    with pytest.raises(InvoicedEntryError):
        await entry_svc.edit_entry(str(entry.id)[:8], now=NOW, note="x")
    with pytest.raises(InvoicedEntryError):
        await entry_svc.delete_entry(str(entry.id)[:8])


async def test_delete_entry(project):
    entry = await entry_svc.log_entry("1h", "api", now=NOW)
    await entry_svc.delete_entry(str(entry.id)[:8])
    assert await entry_svc.list_entries() == []


async def test_list_entries_filters(db):
    await client_svc.create_client("Acme")
    await client_svc.create_client("Beta")
    await project_svc.create_project("API", "acme")
    await project_svc.create_project("Web", "beta")
    await entry_svc.log_entry("yesterday 2h", "api", now=NOW)
    await entry_svc.log_entry("today 1h", "web", now=NOW)

    assert len(await entry_svc.list_entries(client_slug="acme")) == 1
    assert len(await entry_svc.list_entries(project_slug="web")) == 1
    assert len(await entry_svc.list_entries(date_from=NOW.date())) == 1
    assert len(await entry_svc.list_entries(date_to=NOW.date() - timedelta(days=1))) == 1
