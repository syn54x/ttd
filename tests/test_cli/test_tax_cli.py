from _runner import CliRunner
from ttd.cli.app import app

runner = CliRunner()


def _seed_paid_invoice(tmp):
    """4h at $150 → $600 subtotal, paid 2026-05-10 (IRS Q2) at 32% set-aside."""
    runner.invoke(app, ["client", "add", "Acme", "--rate", "150"])
    runner.invoke(app, ["project", "add", "API", "--client", "acme"])
    runner.invoke(app, ["log", "yesterday 9am to 11am", "-p", "api"])
    runner.invoke(app, ["log", "yesterday 1pm to 3pm", "-p", "api"])
    runner.invoke(app, ["config", "set", "tax.set_aside_rate", "0.32"])
    runner.invoke(app, ["invoice", "create", "--client", "acme", "--month", "2026-06"])
    return runner.invoke(app, ["invoice", "mark", "2026-001", "paid", "--paid-date", "2026-05-10"])


def test_mark_paid_reports_set_aside(isolated_config):
    marked = _seed_paid_invoice(isolated_config)
    assert marked.exit_code == 0, marked.output
    assert "set aside $192.00 (32%)" in marked.output
    assert "2026-05-10" in marked.output


def test_status_buckets_into_irs_quarters(isolated_config):
    _seed_paid_invoice(isolated_config)
    status = runner.invoke(app, ["tax", "status", "--year", "2026"])
    assert status.exit_code == 0, status.output
    q2 = next(line for line in status.output.splitlines() if "2026Q2" in line)
    assert "600.00" in q2  # income
    assert "192.00" in q2  # set aside
    assert "Jun 15 2026" in q2  # due date

    # bare `ttd tax` is the same dashboard
    assert "2026Q2" in runner.invoke(app, ["tax"]).output


def test_pay_and_payments_lifecycle(isolated_config):
    _seed_paid_invoice(isolated_config)
    paid = runner.invoke(app, ["tax", "pay", "2026q2", "100", "--note", "EFTPS"])
    assert paid.exit_code == 0, paid.output

    payments = runner.invoke(app, ["tax", "payments"])
    assert "2026Q2" in payments.output
    assert "100.00" in payments.output
    assert "EFTPS" in payments.output

    q2 = next(
        line
        for line in runner.invoke(app, ["tax", "status"]).output.splitlines()
        if "2026Q2" in line
    )
    assert "92.00" in q2  # balance = 192 - 100

    payment_id = payments.output.splitlines()[2].split()[0]
    assert runner.invoke(app, ["tax", "rm", payment_id]).exit_code == 0
    assert "No payments" in runner.invoke(app, ["tax", "payments"]).output


def test_pay_rejects_garbage_quarter(isolated_config):
    _seed_paid_invoice(isolated_config)
    bad = runner.invoke(app, ["tax", "pay", "banana", "5"])
    assert bad.exit_code == 1
    assert "banana" in bad.output


def test_invoice_show_includes_set_aside(isolated_config):
    _seed_paid_invoice(isolated_config)
    show = runner.invoke(app, ["invoice", "show", "2026-001"])
    assert "Set aside (32%)" in show.output
    assert "$192.00" in show.output
    assert "paid 2026-05-10" in show.output


def test_draft_preview_shows_set_aside_hint(isolated_config):
    runner.invoke(app, ["client", "add", "Acme", "--rate", "150"])
    runner.invoke(app, ["project", "add", "API", "--client", "acme"])
    runner.invoke(app, ["log", "yesterday 9am to 11am", "-p", "api"])
    runner.invoke(app, ["config", "set", "tax.set_aside_rate", "0.32"])
    result = runner.invoke(
        app, ["invoice", "create", "--client", "acme", "--month", "2026-06", "--dry-run"]
    )
    assert "Set aside at 32% when paid" in result.output


def test_status_hints_when_unconfigured(isolated_config):
    status = runner.invoke(app, ["tax", "status"])
    assert status.exit_code == 0
    assert "tax.set_aside_rate" in status.output
