from cyclopts import App
from rich.table import Table

from ttd.cli import (
    client_cmds,
    db_cmds,
    entries_cmds,
    export_cmds,
    log_cmds,
    project_cmds,
)
from ttd.cli.console import stdout
from ttd.core.services import health

app = App(name="ttd", help="Terminal-native billable ledger.")

app.command(db_cmds.app)
app.command(client_cmds.app)
app.command(project_cmds.app)
app.command(log_cmds.app)
app.command(entries_cmds.app)
app.command(export_cmds.app)


@app.default
async def health_cmd() -> None:
    """Check service and database connectivity."""
    result = await health.ping()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]status[/bold]", f"[green]{result['status']}[/green]")
    table.add_row("[bold]db[/bold]", str(result["db_path"]))
    stdout.print(table)


def main() -> None:
    import sys

    from ttd.cli.interactive import set_invocation_tokens

    set_invocation_tokens(sys.argv[1:])
    app()
