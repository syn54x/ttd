from _runner import CliRunner
from ttd.cli.app import app

runner = CliRunner()


def _seed(tmp):
    runner.invoke(app, ["client", "add", "Acme", "--rate", "150"])
    runner.invoke(app, ["project", "add", "API", "--client", "acme"])
    runner.invoke(app, ["log", "yesterday 9am to 11am", "-p", "api"])
    runner.invoke(app, ["log", "yesterday 1pm to 3pm", "-p", "api"])
    runner.invoke(app, ["config", "set", "invoice.output_dir", str(tmp / "invoices")])
    runner.invoke(app, ["config", "set", "user.name", "Taylor"])


def test_invoice_create_dry_run(isolated_config):
    _seed(isolated_config)
    result = runner.invoke(
        app, ["invoice", "create", "--client", "acme", "--month", "2026-06", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert "600.00" in result.output  # 4h * 150
    # nothing persisted
    assert "No invoices yet" in runner.invoke(app, ["invoice", "list"]).output


def test_invoice_create_renders_files(isolated_config):
    _seed(isolated_config)
    result = runner.invoke(
        app, ["invoice", "create", "--client", "acme", "--month", "2026-06", "--pdf", "--md"]
    )
    assert result.exit_code == 0, result.output
    assert "2026-001" in result.output
    pdf = isolated_config / "invoices" / "2026-001-acme.pdf"
    md = isolated_config / "invoices" / "2026-001-acme.md"
    assert pdf.is_file() and pdf.read_bytes().startswith(b"%PDF-")
    assert md.is_file() and "# Invoice 2026-001" in md.read_text()


def test_invoice_lifecycle_via_cli(isolated_config):
    _seed(isolated_config)
    runner.invoke(app, ["invoice", "create", "--client", "acme", "--month", "2026-06"])

    listing = runner.invoke(app, ["invoice", "list"])
    assert "2026-001" in listing.output
    assert "draft" in listing.output

    show = runner.invoke(app, ["invoice", "show", "2026-001"])
    assert show.exit_code == 0
    assert "API" in show.output

    assert runner.invoke(app, ["invoice", "mark", "2026-001", "sent"]).exit_code == 0
    assert runner.invoke(app, ["invoice", "mark", "2026-001", "paid"]).exit_code == 0
    assert "paid" in runner.invoke(app, ["invoice", "list"]).output

    bad = runner.invoke(app, ["invoice", "mark", "2026-001", "banana"])
    assert bad.exit_code == 1


def test_invoiced_entries_locked_via_cli(isolated_config):
    _seed(isolated_config)
    runner.invoke(app, ["invoice", "create", "--client", "acme", "--month", "2026-06"])
    listing = runner.invoke(app, ["entry", "list"]).output
    uid = listing.splitlines()[2].split()[0]
    result = runner.invoke(app, ["entry", "rm", uid])
    assert result.exit_code == 1
    assert "invoice" in result.output
    # void releases them
    runner.invoke(app, ["invoice", "mark", "2026-001", "void"])
    assert runner.invoke(app, ["entry", "rm", uid]).exit_code == 0
