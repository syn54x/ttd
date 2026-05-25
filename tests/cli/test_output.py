"""CLI formatters tolerate ferro text enum hydration."""

from decimal import Decimal

from ttd.cli.output import print_entries, print_projects
from ttd.core.models.enums import BillingMode
from ttd.core.schemas import CreateProject
from ttd.core.services import projects as project_service


async def test_print_projects_with_string_billing_mode(
    db, sample_client, capsys
) -> None:
    await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Website",
            billing_mode=BillingMode.HOURLY,
        )
    )
    projects = await project_service.list_projects_for_client(sample_client.id)
    # Simulate ferro DB read returning str
    projects[0].billing_mode = "hourly"  # type: ignore[misc]
    print_projects(projects)
    out = capsys.readouterr().out
    assert "Website" in out
    assert "hourly" in out


async def test_print_entries_with_string_entry_mode(db, hourly_project, capsys) -> None:
    from datetime import date

    from ttd.core.schemas import CreateDurationEntry
    from ttd.core.services import time_entries as entry_service

    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date=date(2026, 5, 1),
            billable_hours=Decimal("2"),
        )
    )
    entries = await entry_service.list_time_entries_for_project(hourly_project.id)
    entries[0].entry_mode = "duration"  # type: ignore[misc]
    print_entries(entries)
    out = capsys.readouterr().out
    assert "2.00h" in out
