from _runner import CliRunner
from ttd.cli.app import app

runner = CliRunner()


def _seed():
    runner.invoke(app, ["client", "add", "Acme", "--rate", "150"])
    runner.invoke(app, ["project", "add", "API", "--client", "acme"])
    runner.invoke(app, ["log", "today 9am to 11am", "-p", "api", "--note", "sync"])
    runner.invoke(app, ["log", "today 1pm to 3pm", "-p", "api"])


def test_report_day(isolated_config):
    _seed()
    result = runner.invoke(app, ["report", "day"])
    assert result.exit_code == 0, result.output
    assert "acme/api" in result.output
    assert "4:00" in result.output
    assert "600" in result.output  # 4h * $150


def test_report_week_by_project(isolated_config):
    _seed()
    result = runner.invoke(app, ["report", "week"])
    assert result.exit_code == 0, result.output
    assert "acme/api" in result.output
    assert "Total" in result.output


def test_report_week_by_client(isolated_config):
    _seed()
    result = runner.invoke(app, ["report", "week", "--by", "client"])
    assert result.exit_code == 0, result.output
    assert "acme" in result.output


def test_report_tax_columns_with_rate(isolated_config):
    _seed()
    runner.invoke(app, ["config", "set", "tax.set_aside_rate", "0.32"])
    result = runner.invoke(app, ["report", "week"])
    assert result.exit_code == 0, result.output
    assert "Est. Tax" in result.output
    assert "192.00" in result.output  # 32% of $600
    assert "408.00" in result.output  # take-home
    assert "est. tax" in result.output  # totals line
    assert "take-home" in result.output


def test_report_tax_summary_in_day_view(isolated_config):
    _seed()
    runner.invoke(app, ["config", "set", "tax.set_aside_rate", "0.32"])
    result = runner.invoke(app, ["report", "day"])
    assert result.exit_code == 0, result.output
    assert "Est. Tax" not in result.output  # day view keeps per-row columns lean
    assert "est. tax" in result.output
    assert "take-home" in result.output


def test_report_hides_tax_columns_without_rate(isolated_config):
    _seed()
    result = runner.invoke(app, ["report", "week"])
    assert result.exit_code == 0, result.output
    assert "Est. Tax" not in result.output
    assert "take-home" not in result.output


def test_report_month_empty(isolated_config):
    runner.invoke(app, ["client", "add", "Acme"])
    result = runner.invoke(app, ["report", "month", "--last"])
    assert result.exit_code == 0
    assert "No entries" in result.output


def test_report_range_and_validation(isolated_config):
    _seed()
    ok = runner.invoke(app, ["report", "range", "--from", "2026-01-01", "--to", "2026-12-31"])
    assert ok.exit_code == 0
    bad = runner.invoke(app, ["report", "range", "--from", "nope", "--to", "2026-12-31"])
    assert bad.exit_code == 1
    assert "YYYY-MM-DD" in bad.output


def test_report_by_rejects_unknown(isolated_config):
    _seed()
    result = runner.invoke(app, ["report", "week", "--by", "banana"])
    assert result.exit_code == 1


def test_report_week_with_entries(isolated_config):
    _seed()
    result = runner.invoke(app, ["report", "week", "--entries"])
    assert result.exit_code == 0, result.output
    assert "acme/api" in result.output
    assert "sync" in result.output
    assert "Total" in result.output


def test_report_entries_requires_by_project(isolated_config):
    _seed()
    result = runner.invoke(app, ["report", "week", "--entries", "--by", "client"])
    assert result.exit_code == 1
    assert "--entries requires --by project" in result.output
