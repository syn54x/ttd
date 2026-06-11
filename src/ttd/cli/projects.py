"""`ttd project …` commands."""

from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field

from ttd.cli._interactive import interactive_fill
from ttd.cli._output import console, success, table
from ttd.cli._pickers import client_choices, validate_money
from ttd.cli._run import TtdApp, with_db
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours, format_money, parse_money
from ttd.services import projects as svc
from ttd.storage.models import Client

app = TtdApp(name="project", help="Manage projects.")

ClientOpt = Annotated[str | None, Parameter(name="--client", help="Client slug")]
InteractiveOpt = Annotated[
    bool, Parameter(name=["--interactive", "-i"], help="Fill remaining fields via a form")
]


def _default_client(client: str | None) -> str:
    if client is not None:
        return client
    if configured := get_settings().defaults.client:
        return configured
    raise TtdError("No client given and no [defaults].client in config — pass --client")


class ProjectAddInput(BaseModel):
    name: str = Field(json_schema_extra={"prompt": "Project name"})
    client: str = Field(
        json_schema_extra={"prompt": "Client", "widget": "select", "choices": client_choices}
    )
    rate: str | None = Field(
        None,
        json_schema_extra={
            "prompt": "Hourly rate (blank to inherit client rate)",
            "validate": validate_money,
        },
    )


@app.command(name="add")
@with_db
async def add(
    name: Annotated[str | None, Parameter(help="Project display name")] = None,
    *,
    client: ClientOpt = None,
    rate: Annotated[str | None, Parameter(help="Hourly rate override")] = None,
    slug: str | None = None,
    interactive: InteractiveOpt = False,
) -> None:
    """Add a project under a client."""
    if interactive:
        data = await interactive_fill(
            ProjectAddInput, {"name": name, "client": client, "rate": rate}
        )
        name, client, rate = data.name, data.client, data.rate
    if name is None:
        raise TtdError("NAME is required (or use -i for the interactive form)")

    project = await svc.create_project(
        name,
        _default_client(client),
        slug=slug,
        hourly_rate=parse_money(rate) if rate else None,
    )
    success(f"Added project [accent]{project.name}[/accent] ({project.slug})")


@app.command(name="list")
@with_db
async def list_(
    *,
    client: ClientOpt = None,
    archived: bool = False,
) -> None:
    """List projects with effective rates and logged hours."""
    projects = await svc.list_projects(client, include_archived=archived)
    clients = {c.id: c for c in await Client.all()}
    rows = []
    for p in projects:
        c = clients.get(p.client_id)
        rate = await svc.effective_rate(p)
        seconds = await svc.entry_seconds(p)
        unbilled = await svc.entry_seconds(p, uninvoiced_only=True)
        rows.append((p, c, rate, seconds, unbilled))

    if not rows:
        console.print("[muted]No projects yet — `ttd project add NAME --client SLUG`[/muted]")
        return
    t = table("Client", "Slug", "Name", "Rate", "Logged", "Unbilled")
    for p, c, rate, seconds, unbilled in rows:
        currency = c.currency if c else "USD"
        rate_s = format_money(rate, currency) if rate is not None else "—"
        inherited = " [muted](client)[/muted]" if p.hourly_rate is None and rate is not None else ""
        name = p.name if p.archived_at is None else f"[muted]{p.name} (archived)[/muted]"
        t.add_row(
            c.slug if c else "?",
            p.slug,
            name,
            rate_s + inherited,
            format_hours(seconds),
            format_hours(unbilled),
        )
    console.print(t)


@app.command(name="edit")
@with_db
async def edit(
    slug: str,
    *,
    client: ClientOpt = None,
    name: str | None = None,
    new_slug: Annotated[str | None, Parameter(name="--slug")] = None,
    rate: str | None = None,
) -> None:
    """Edit a project."""
    project = await svc.update_project(
        slug,
        client,
        name=name,
        new_slug=new_slug,
        hourly_rate=parse_money(rate) if rate else None,
    )
    success(f"Updated project {project.slug}")


@app.command(name="archive")
@with_db
async def archive(
    slug: str,
    *,
    client: ClientOpt = None,
) -> None:
    """Archive a project."""
    project = await svc.archive_project(slug, client)
    success(f"Archived project {project.slug}")
