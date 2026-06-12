from _runner import CliRunner
from ttd.cli.app import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("ttd ")


def test_install_completion_registered():
    """The installation docs document `ttd --install-completion`; keep it real."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--install-completion" in result.output


def test_client_add_list_roundtrip(isolated_config):
    result = runner.invoke(
        app, ["client", "add", "Acme Corp", "--rate", "150", "--email", "a@b.co"]
    )
    assert result.exit_code == 0, result.output
    assert "acme-corp" in result.output

    result = runner.invoke(app, ["client", "list"])
    assert result.exit_code == 0
    assert "Acme Corp" in result.output
    assert "150" in result.output


def test_duplicate_client_fails_cleanly(isolated_config):
    assert runner.invoke(app, ["client", "add", "Acme"]).exit_code == 0
    result = runner.invoke(app, ["client", "add", "Acme"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_project_add_and_list(isolated_config):
    runner.invoke(app, ["client", "add", "Acme", "--rate", "150"])
    result = runner.invoke(app, ["project", "add", "API Rewrite", "--client", "acme"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == 0
    assert "api-rewrite" in result.output
    assert "(client)" in result.output  # inherited rate marker


def test_project_uses_configured_default_client(isolated_config):
    runner.invoke(app, ["client", "add", "Acme"])
    assert (
        runner.invoke(app, ["config", "set", "defaults.client", "acme", "--local"]).exit_code == 0
    )
    result = runner.invoke(app, ["project", "add", "API"])
    assert result.exit_code == 0, result.output


def test_project_without_client_or_default_errors(isolated_config):
    result = runner.invoke(app, ["project", "add", "API"])
    assert result.exit_code == 1
    assert "--client" in result.output


def test_config_list_with_origin(isolated_config):
    runner.invoke(app, ["config", "set", "business.currency", "EUR"])
    result = runner.invoke(app, ["config", "list", "--origin"])
    assert result.exit_code == 0
    assert "EUR" in result.output
    assert "global" in result.output


def test_config_list_shows_descriptions(isolated_config):
    result = runner.invoke(app, ["config", "list"])
    assert result.exit_code == 0
    assert "Description" in result.output
    assert "Billing increment" in result.output


def test_every_config_key_has_a_description():
    from ttd.cli.config_cmds import _descriptions, _flatten
    from ttd.config.schema import Settings

    keys = set(_flatten(Settings().model_dump(mode="json")))
    descriptions = _descriptions()
    assert set(descriptions) == keys
    missing = [k for k, d in descriptions.items() if not d]
    assert not missing, f"config fields missing a description: {missing}"


def test_db_doctor(isolated_config):
    runner.invoke(app, ["client", "add", "Acme"])
    result = runner.invoke(app, ["db", "doctor"])
    assert result.exit_code == 0
    assert "clients: 1" in result.output


def test_seed_demo_includes_today(isolated_config):
    from datetime import date

    result = runner.invoke(app, ["db", "seed-demo", "--yes"])
    assert result.exit_code == 0, result.output

    today = date.today().isoformat()
    listing = runner.invoke(app, ["entry", "list", "--from", today, "--to", today])
    assert listing.exit_code == 0
    # column text may be truncated by table width; notes and total are stable
    assert "deep work" in listing.output  # today's seeded api-rewrite entry
    assert "reviews" in listing.output  # today's seeded design-system entry
    assert "Total: 4:00" in listing.output


def test_seed_demo_reset_wipes_existing_data(isolated_config):
    runner.invoke(app, ["client", "add", "Existing Client"])
    assert runner.invoke(app, ["db", "seed-demo", "--yes"]).exit_code == 0

    # without --reset, reseeding collides with the demo clients
    again = runner.invoke(app, ["db", "seed-demo", "--yes"])
    assert again.exit_code == 1
    assert "already exists" in again.output

    result = runner.invoke(app, ["db", "seed-demo", "--yes", "--reset"])
    assert result.exit_code == 0, result.output

    listing = runner.invoke(app, ["client", "list"]).output
    assert "Existing Client" not in listing
    assert "Acme Corp" in listing
