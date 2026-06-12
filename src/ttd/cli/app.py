"""Root Cyclopts application.

Bare ``ttd`` launches the TUI; subcommands cover everything non-interactively.
"""

import ttd
from ttd.cli._run import TtdApp

app = TtdApp(
    name="ttd",
    help="Terminal-first time tracking, reporting, and invoicing.",
    version=f"ttd {ttd.__version__}",
    version_flags=["--version", "-V"],
)


def _register_subcommands() -> None:
    from ttd.cli import (
        clients,
        config_cmds,
        db_cmds,
        entries,
        export,
        import_,
        invoices,
        log,
        projects,
        reports,
        taxes,
        timer,
    )

    app.command(clients.app)
    app.command(projects.app)
    app.command(entries.app)
    app.command(reports.app)
    app.command(invoices.app)
    app.command(taxes.app)
    app.command(config_cmds.app)
    app.command(db_cmds.app)
    timer.register(app)
    log.register(app)
    export.register(app)
    import_.register(app)


_register_subcommands()
app.register_install_completion_command()


@app.default
def root() -> None:
    """Launch the TUI when no subcommand is given."""
    from ttd.tui.app import run_tui

    run_tui()


def main() -> None:
    app()
