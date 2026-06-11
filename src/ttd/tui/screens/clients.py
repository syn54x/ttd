"""Clients & projects: tree with rates/unbilled hours, full CRUD."""

from decimal import Decimal
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Tree

from ttd.core.errors import TtdError
from ttd.core.money import format_money, parse_money
from ttd.services import clients as client_svc
from ttd.services import projects as project_svc
from ttd.tui._data import client_tree
from ttd.tui.screens._base import TtdScreen
from ttd.tui.widgets.forms import FormField, FormModal
from ttd.tui.widgets.modals import ConfirmModal


def _validate_money(text: str) -> bool | str:
    try:
        parse_money(text)
    except TtdError as exc:
        return str(exc)
    return True


def _rate(raw: str | None) -> Decimal | None:
    return parse_money(raw) if raw else None


class ClientsScreen(TtdScreen):
    nav_id = "clients"

    BINDINGS: ClassVar = [
        *TtdScreen.BINDINGS,
        ("a", "add_client", "add client"),
        ("p", "add_project", "add project"),
        ("e", "edit_node", "edit"),
        ("x", "archive_node", "archive"),
        ("D", "delete_node", "delete"),
    ]

    def compose_content(self) -> ComposeResult:
        with Vertical(id="clients"):
            yield Label("clients & projects", classes="section-title")
            yield Tree("portfolio", id="client-tree")
            yield Label("", id="clients-help", classes="muted")

    async def render_data(self) -> None:
        tree = self.query_one("#client-tree", Tree)
        tree.clear()
        tree.show_root = False
        nodes = await client_tree()
        if not nodes:
            tree.root.add_leaf("no clients yet — press a to add one")
        for node in nodes:
            client = node["client"]
            rate = (
                format_money(client.hourly_rate, client.currency)
                if client.hourly_rate is not None
                else "—"
            )
            branch = tree.root.add(
                f"[bold]{client.name}[/bold] [dim]({client.slug}) · default {rate}/h[/dim]",
                expand=True,
                data=("client", client.slug),
            )
            if not node["projects"]:
                branch.add_leaf("[dim]no projects — press p[/dim]")
            for item in node["projects"]:
                p = item["project"]
                branch.add_leaf(
                    f"{p.name} [dim]({p.slug})[/dim] · {item['rate']}/h · "
                    f"[#ffb000]{item['unbilled']}[/#ffb000] unbilled",
                    data=("project", client.slug, p.slug),
                )
        self.query_one("#clients-help", Label).update(
            "[dim]a add client · p add project · e edit · x archive · D delete[/dim]"
        )

    def _selected(self) -> tuple | None:
        node = self.query_one("#client-tree", Tree).cursor_node
        return node.data if node is not None else None

    # --- forms ---------------------------------------------------------------

    def _client_fields(self, client=None) -> list[FormField]:
        return [
            FormField("name", "Name", value=client.name if client else None, required=True),
            FormField(
                "rate",
                "Default hourly rate (blank for none)",
                value=str(client.hourly_rate) if client and client.hourly_rate else None,
                validate=_validate_money,
            ),
            FormField("currency", "Currency", value=client.currency if client else "USD"),
            FormField("contact", "Contact name", value=client.contact_name if client else None),
            FormField("email", "Email", value=client.email if client else None),
            FormField("address", "Address", value=client.address if client else None),
        ]

    async def action_add_client(self) -> None:
        async def _save(values: dict | None) -> None:
            if values is None:
                return
            try:
                client = await client_svc.create_client(
                    values["name"],
                    hourly_rate=_rate(values["rate"]),
                    currency=values["currency"] or "USD",
                    contact_name=values["contact"] or None,
                    email=values["email"] or None,
                    address=values["address"] or None,
                )
                self.notify(f"added {client.slug}")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(FormModal("add client", self._client_fields()), _save)

    async def action_add_project(self) -> None:
        clients = await client_svc.list_clients()
        if not clients:
            self.notify("add a client first", severity="warning")
            return
        selected = self._selected()
        preselect = None
        if (selected and selected[0] == "client") or (selected and selected[0] == "project"):
            preselect = selected[1]
        fields = [
            FormField("name", "Name", required=True),
            FormField(
                "client",
                "Client",
                kind="select",
                value=preselect,
                choices=[(c.slug, f"{c.name} ({c.slug})") for c in clients],
                required=True,
            ),
            FormField(
                "rate",
                "Hourly rate (blank to inherit client rate)",
                validate=_validate_money,
            ),
        ]

        async def _save(values: dict | None) -> None:
            if values is None:
                return
            try:
                project = await project_svc.create_project(
                    values["name"], values["client"], hourly_rate=_rate(values["rate"])
                )
                self.notify(f"added {values['client']}/{project.slug}")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(FormModal("add project", fields), _save)

    async def action_edit_node(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        if selected[0] == "client":
            await self._edit_client(selected[1])
        elif selected[0] == "project":
            await self._edit_project(selected[1], selected[2])

    async def _edit_client(self, slug: str) -> None:
        client = await client_svc.get_client(slug)

        async def _save(values: dict | None) -> None:
            if values is None:
                return
            try:
                await client_svc.update_client(
                    slug,
                    name=values["name"],
                    hourly_rate=_rate(values["rate"]),
                    currency=values["currency"] or None,
                    contact_name=values["contact"] or None,
                    email=values["email"] or None,
                    address=values["address"] or None,
                )
                self.notify(f"updated {slug}")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(FormModal(f"edit client {slug}", self._client_fields(client)), _save)

    async def _edit_project(self, client_slug: str, slug: str) -> None:
        project = await project_svc.get_project(slug, client_slug)
        fields = [
            FormField("name", "Name", value=project.name, required=True),
            FormField(
                "rate",
                "Hourly rate (blank to inherit client rate)",
                value=str(project.hourly_rate) if project.hourly_rate else None,
                validate=_validate_money,
            ),
        ]

        async def _save(values: dict | None) -> None:
            if values is None:
                return
            try:
                await project_svc.update_project(
                    slug,
                    client_slug,
                    name=values["name"],
                    hourly_rate=_rate(values["rate"]),
                )
                self.notify(f"updated {client_slug}/{slug}")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(FormModal(f"edit project {client_slug}/{slug}", fields), _save)

    async def action_archive_node(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        label = selected[1] if selected[0] == "client" else f"{selected[1]}/{selected[2]}"

        async def _confirmed(yes: bool | None) -> None:
            if not yes:
                return
            try:
                if selected[0] == "client":
                    await client_svc.archive_client(selected[1])
                else:
                    await project_svc.archive_project(selected[2], selected[1])
                self.notify(f"archived {label}")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(
            ConfirmModal(f"Archive {label}? (hidden from lists, history kept)"), _confirmed
        )

    async def action_delete_node(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        if selected[0] == "client":
            message = (
                f"DELETE client '{selected[1]}' and ALL its projects and entries?\n"
                "Invoiced work is protected and will block this."
            )
        else:
            message = (
                f"DELETE project '{selected[1]}/{selected[2]}' and all its entries?\n"
                "Invoiced work is protected and will block this."
            )

        async def _confirmed(yes: bool | None) -> None:
            if not yes:
                return
            try:
                if selected[0] == "client":
                    await client_svc.delete_client(selected[1], force=True)
                else:
                    await project_svc.delete_project(selected[2], selected[1], force=True)
                self.notify("deleted")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(ConfirmModal(message), _confirmed)
