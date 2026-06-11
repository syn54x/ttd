"""`ttd client …` commands."""

from decimal import Decimal
from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field
from rich.prompt import Confirm

from ttd.cli._interactive import interactive_fill
from ttd.cli._output import console, success, table
from ttd.cli._pickers import validate_money
from ttd.cli._run import TtdApp, abort, with_db
from ttd.core.errors import TtdError
from ttd.core.money import format_money, parse_money
from ttd.services import clients as svc

app = TtdApp(name="client", help="Manage clients.")

RateOpt = Annotated[str | None, Parameter(help="Default hourly rate, e.g. 150")]
InteractiveOpt = Annotated[
    bool, Parameter(name=["--interactive", "-i"], help="Fill remaining fields via a form")
]


def _rate(raw: str | None) -> Decimal | None:
    return parse_money(raw) if raw is not None else None


class ClientAddInput(BaseModel):
    name: str = Field(json_schema_extra={"prompt": "Client name"})
    rate: str | None = Field(
        None,
        json_schema_extra={"prompt": "Hourly rate (blank for none)", "validate": validate_money},
    )
    currency: str = Field("USD", json_schema_extra={"prompt": "Currency"})
    contact: str | None = Field(None, json_schema_extra={"prompt": "Contact name (optional)"})
    email: str | None = Field(None, json_schema_extra={"prompt": "Email (optional)"})
    address: str | None = Field(None, json_schema_extra={"prompt": "Address (optional)"})


@app.command(name="add")
@with_db
async def add(
    name: Annotated[str | None, Parameter(help="Client display name")] = None,
    *,
    rate: RateOpt = None,
    currency: str | None = None,
    slug: Annotated[str | None, Parameter(help="Override the generated slug")] = None,
    contact: str | None = None,
    email: str | None = None,
    address: str | None = None,
    interactive: InteractiveOpt = False,
) -> None:
    """Add a client."""
    if interactive:
        data = await interactive_fill(
            ClientAddInput,
            {
                "name": name,
                "rate": rate,
                "currency": currency,
                "contact": contact,
                "email": email,
                "address": address,
            },
        )
        name, rate, currency = data.name, data.rate, data.currency
        contact, email, address = data.contact, data.email, data.address
    if name is None:
        raise TtdError("NAME is required (or use -i for the interactive form)")
    client = await svc.create_client(
        name,
        slug=slug,
        hourly_rate=_rate(rate),
        currency=currency or "USD",
        contact_name=contact,
        email=email,
        address=address,
    )
    success(f"Added client [accent]{client.name}[/accent] ({client.slug})")


@app.command(name="list")
@with_db
async def list_(
    *,
    archived: Annotated[bool, Parameter(help="Include archived")] = False,
) -> None:
    """List clients."""
    clients = await svc.list_clients(include_archived=archived)
    if not clients:
        console.print("[muted]No clients yet — `ttd client add NAME`[/muted]")
        return
    t = table("Slug", "Name", "Rate", "Currency", "Contact")
    for c in clients:
        rate = format_money(c.hourly_rate, c.currency) if c.hourly_rate is not None else "—"
        name = c.name if c.archived_at is None else f"[muted]{c.name} (archived)[/muted]"
        t.add_row(c.slug, name, rate, c.currency, c.email or c.contact_name or "")
    console.print(t)


@app.command(name="edit")
@with_db
async def edit(
    slug: str,
    *,
    name: str | None = None,
    new_slug: Annotated[str | None, Parameter(name="--slug")] = None,
    rate: RateOpt = None,
    currency: str | None = None,
    contact: str | None = None,
    email: str | None = None,
    address: str | None = None,
) -> None:
    """Edit a client."""
    client = await svc.update_client(
        slug,
        name=name,
        new_slug=new_slug,
        hourly_rate=_rate(rate),
        currency=currency,
        contact_name=contact,
        email=email,
        address=address,
    )
    success(f"Updated client {client.slug}")


@app.command(name="archive")
@with_db
async def archive(slug: str) -> None:
    """Archive a client (hidden from lists, history kept)."""
    client = await svc.archive_client(slug)
    success(f"Archived client {client.slug}")


@app.command(name="rm")
@with_db
async def rm(
    slug: str,
    *,
    force: Annotated[bool, Parameter(help="Also delete projects and entries")] = False,
) -> None:
    """Delete a client. Refuses if it has projects unless --force."""
    if force and not Confirm.ask(f"Delete client '{slug}' and ALL its projects/entries?"):
        abort()
    await svc.delete_client(slug, force=force)
    success(f"Deleted client {slug}")
