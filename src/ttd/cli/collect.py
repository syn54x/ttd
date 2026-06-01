"""Interactive field collection for CLI mutating commands."""

from __future__ import annotations

from datetime import date
from typing import Literal, cast

from ttd.cli import prompts
from ttd.cli.inputs import (
    ClientAddInput,
    ClientDeleteInput,
    ClientUpdateInput,
    ConfigInitInput,
    EntryDeleteInput,
    EntryEditInput,
    LogEntryInput,
    ProjectAddInput,
    ProjectDeleteInput,
    ProjectUpdateInput,
)
from ttd.cli.pickers import (
    confirm_delete,
    pick_client,
    pick_entry_for_project,
    pick_project_any,
    pick_project_for_client,
)
from ttd.cli.runtime import require_id, resolve_client
from ttd.core.exceptions import ValidationError
from ttd.core.models.client import Client
from ttd.core.models.enums import BillingMode, EntryMode
from ttd.core.models.project import Project
from ttd.core.models.time_entry import TimeEntry
from ttd.core.services import clients as client_service
from ttd.core.services import projects as project_service
from ttd.core.services import time_entries as entry_service
from ttd.core.time import parse_interval_parts, parse_interval_phrase, parse_work_date


async def collect_client_add(values: ClientAddInput) -> ClientAddInput:
    if values.name is None:
        values.name = await prompts.ask_text("Client name")
    if values.rate is None:
        values.rate = await prompts.ask_text("Default hourly rate")
    if values.currency is None:
        values.currency = await prompts.ask_text("Currency (ISO code)", default="USD")
    return values


async def collect_client_update(values: ClientUpdateInput) -> ClientUpdateInput:
    client: Client | None = None
    if values.client_id is not None:
        client = await client_service.get_client(values.client_id)
    if client is None:
        client = await pick_client(message="Client to update")
        values.client_id = client.id

    field_choices = [
        ("Name", "name"),
        ("Default hourly rate", "rate"),
        ("Currency", "currency"),
    ]
    fields = await prompts.ask_checkbox("Fields to change", field_choices)

    for field in fields:
        if field == "name" and values.name is None:
            values.name = await prompts.ask_text("New name", default=client.name)
        elif field == "rate" and values.rate is None:
            values.rate = await prompts.ask_text("New default hourly rate")
        elif field == "currency" and values.currency is None:
            values.currency = await prompts.ask_text(
                "New currency", default=client.currency
            )
    return values


async def collect_client_delete(values: ClientDeleteInput) -> ClientDeleteInput:
    label: str
    if values.client_id is None:
        client = await pick_client(message="Client to delete")
        values.client_id = client.id
        label = client.name
    else:
        label = str(values.client_id)[:8]

    if not await confirm_delete(f"client {label}"):
        values.cancelled = True
    return values


def _parse_billing_mode(value: str) -> BillingMode:
    normalized = value.strip().lower().replace("-", "_")
    return BillingMode(normalized)


async def collect_project_add(values: ProjectAddInput) -> ProjectAddInput:
    client: Client | None = None
    if values.client is None:
        client = await pick_client(message="Client")
        values.client = client.name

    if values.name is None:
        values.name = await prompts.ask_text("Project name")

    if values.billing_mode is None:
        mode_key = await prompts.ask_select(
            "Billing mode",
            [
                ("Hourly (time & materials)", "hourly"),
                ("Fixed price (contract total)", "fixed_price"),
            ],
        )
        values.billing_mode = mode_key

    mode = _parse_billing_mode(str(values.billing_mode))
    if mode == BillingMode.HOURLY:
        if values.rate is None:
            rate = await prompts.ask_text(
                "Hourly rate (leave empty to inherit from client)", default=""
            )
            values.rate = rate if rate else None
        if values.currency is None and values.rate:
            values.currency = await prompts.ask_text(
                "Currency (ISO code)", default="USD"
            )
    else:
        if values.contract_total is None:
            values.contract_total = await prompts.ask_text("Contract total")
        if values.currency is None:
            values.currency = await prompts.ask_text(
                "Currency (ISO code)", default="USD"
            )

    if values.soft_max_hours is None:
        soft = await prompts.ask_text(
            "Soft max hours (optional, Enter to skip)", default=""
        )
        values.soft_max_hours = soft if soft else None
    return values


async def collect_project_update(values: ProjectUpdateInput) -> ProjectUpdateInput:
    project: Project | None = None
    if values.project_id is not None:
        project = await project_service.get_project(values.project_id)
    if project is None:
        project = await pick_project_any(message="Project to update")
        values.project_id = project.id

    field_choices = [
        ("Name", "name"),
        ("Hourly rate", "rate"),
        ("Currency", "currency"),
        ("Contract total", "contract_total"),
        ("Soft max hours", "soft_max_hours"),
        ("Clear rate override", "clear_rate_override"),
    ]
    fields = await prompts.ask_checkbox("Fields to change", field_choices)

    for field in fields:
        if field == "name" and values.name is None:
            values.name = await prompts.ask_text("New name", default=project.name)
        elif field == "rate" and values.rate is None:
            values.rate = await prompts.ask_text("New hourly rate")
        elif field == "currency" and values.currency is None:
            values.currency = await prompts.ask_text("New currency")
        elif field == "contract_total" and values.contract_total is None:
            values.contract_total = await prompts.ask_text("New contract total")
        elif field == "soft_max_hours" and values.soft_max_hours is None:
            values.soft_max_hours = await prompts.ask_text("New soft max hours")
        elif field == "clear_rate_override":
            values.clear_rate_override = True
    return values


async def collect_project_delete(values: ProjectDeleteInput) -> ProjectDeleteInput:
    label: str
    if values.project_id is None:
        project = await pick_project_any(message="Project to delete")
        values.project_id = project.id
        label = project.name
    else:
        label = str(values.project_id)[:8]

    if not await confirm_delete(f"project {label}"):
        values.cancelled = True
    return values


async def collect_log_entry(values: LogEntryInput) -> LogEntryInput:
    if values.client is None and values.project_id is None:
        picked = await pick_client(message="Client")
        values.client = picked.name

    if values.project_id is None and values.project is None:
        if values.client is not None:
            owner = await resolve_client(client_id=None, client_name=values.client)
            project = await pick_project_for_client(
                require_id(owner.id, "client"),
                message="Project",
            )
        else:
            project = await pick_project_any(message="Project")
        values.project = project.name
        values.project_id = project.id

    has_hours = values.hours is not None
    has_when = values.when is not None
    has_interval_parts = values.time_from is not None or values.time_to is not None

    if not has_hours and not has_when and not has_interval_parts:
        mode = await prompts.ask_select(
            "Entry type",
            [
                ("Duration (hours)", "duration"),
                ("Interval (e.g. today 8am to 5pm)", "interval"),
            ],
        )
        if mode == "duration":
            if values.work_date is None:
                default_day = date.today().isoformat()
                values.work_date = await prompts.ask_text(
                    "Work date (today, YYYY-MM-DD)", default=default_day
                )
            parse_work_date(values.work_date)
            if values.hours is None:
                values.hours = await prompts.ask_text("Billable hours")
        elif values.when is None:
            values.when = await prompts.ask_text("Interval (e.g. today 8am to 5pm)")
            parse_interval_phrase(values.when)
    elif has_hours:
        if values.work_date is None:
            default_day = date.today().isoformat()
            values.work_date = await prompts.ask_text(
                "Work date (today, YYYY-MM-DD)", default=default_day
            )
        parse_work_date(values.work_date)
    elif has_when:
        when = values.when
        if when is None:
            raise ValidationError("Interval phrase is required")
        parse_interval_phrase(when)
    elif has_interval_parts:
        if values.work_date is None:
            default_day = date.today().isoformat()
            values.work_date = await prompts.ask_text(
                "Work date (today, YYYY-MM-DD)", default=default_day
            )
        if values.time_from is None:
            values.time_from = await prompts.ask_text("Start (e.g. 9am)")
        if values.time_to is None:
            values.time_to = await prompts.ask_text("End (e.g. 5pm)")
        if (
            values.work_date is None
            or values.time_from is None
            or values.time_to is None
        ):
            raise ValidationError("Work date and interval bounds are required")
        parse_interval_parts(
            work_date=values.work_date,
            time_from=values.time_from,
            time_to=values.time_to,
        )

    if values.note is None:
        note = await prompts.ask_text("Note (optional)", default="")
        values.note = note if note else None

    if values.non_billable is None:
        values.non_billable = not await prompts.ask_confirm("Billable?", default=True)
    return values


async def collect_entry_edit(values: EntryEditInput) -> EntryEditInput:
    entry: TimeEntry | None = None
    if values.entry_id is not None:
        entry = await entry_service.get_time_entry(values.entry_id)
    if entry is None:
        project = await pick_project_any(message="Project")
        entry = await pick_entry_for_project(
            require_id(project.id, "project"),
            project_name=project.name,
            message="Entry to edit",
        )
        values.entry_id = entry.id

    field_choices = [
        ("Work date", "work_date"),
        ("Hours / interval", "times"),
        ("Note", "note"),
        ("Billable flag", "billable"),
    ]
    fields = await prompts.ask_checkbox("Fields to change", field_choices)

    for field in fields:
        if field == "work_date" and values.work_date is None:
            values.work_date = await prompts.ask_text(
                "Work date (YYYY-MM-DD)", default=entry.work_date.isoformat()
            )
        elif field == "times":
            if entry.entry_mode == EntryMode.DURATION:
                if values.hours is None:
                    values.hours = await prompts.ask_text("Billable hours")
            else:
                if values.time_from is None:
                    values.time_from = await prompts.ask_text("Start (HH:MM UTC)")
                if values.time_to is None:
                    values.time_to = await prompts.ask_text("End (HH:MM UTC)")
        elif field == "note" and values.note is None:
            values.note = await prompts.ask_text("Note", default=entry.note or "")
        elif (
            field == "billable"
            and values.billable is None
            and values.non_billable is None
        ):
            values.billable = await prompts.ask_confirm(
                "Billable?", default=entry.billable
            )
    return values


async def collect_entry_delete(values: EntryDeleteInput) -> EntryDeleteInput:
    label: str
    if values.entry_id is None:
        project = await pick_project_any(message="Project")
        entry = await pick_entry_for_project(
            require_id(project.id, "project"),
            project_name=project.name,
            message="Entry to delete",
        )
        values.entry_id = entry.id
        label = f"{project.name} · {entry.work_date.isoformat()}"
    else:
        label = str(values.entry_id)[:8]

    if not await confirm_delete(f"entry {label}"):
        values.cancelled = True
    return values


async def collect_config_init(*, global_: bool) -> ConfigInitInput:
    from ttd.core.config import (
        config_file_has_settings,
        config_target_path,
        default_data_dir_path,
        validate_config_value,
    )

    target = config_target_path(global_=global_)
    if config_file_has_settings(target):
        overwrite = await prompts.ask_confirm(
            f"Config already exists at {target}. Overwrite all settings?",
            default=False,
        )
        if not overwrite:
            raise ValidationError("Cancelled; config file unchanged.")

    data_dir = await prompts.ask_text(
        "Data directory",
        default=str(default_data_dir_path()),
    )
    while True:
        try:
            validate_config_value("data_dir", data_dir)
            break
        except ValidationError as exc:
            data_dir = await prompts.ask_text(str(exc))

    db_filename = await prompts.ask_text("Database filename", default="ttd.db")
    while True:
        try:
            validate_config_value("db_filename", db_filename)
            break
        except ValidationError as exc:
            db_filename = await prompts.ask_text(str(exc))

    clock_format = await prompts.ask_select(
        "Clock format",
        [("24-hour", "24h"), ("12-hour", "12h")],
    )

    create_data_dir = await prompts.ask_confirm(
        f"Create data directory {data_dir} if needed?",
        default=True,
    )
    run_migrate = await prompts.ask_confirm(
        "Apply database schema now?",
        default=True,
    )

    return ConfigInitInput(
        data_dir=data_dir,
        db_filename=db_filename,
        clock_format=cast(Literal["12h", "24h"], clock_format),
        create_data_dir=create_data_dir,
        run_migrate=run_migrate,
    )
