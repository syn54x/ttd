from _runner import CliRunner
from ttd.cli.app import app

runner = CliRunner()


def _setup(tmp):
    runner.invoke(app, ["client", "add", "Acme", "--rate", "150"])
    runner.invoke(app, ["project", "add", "API", "--client", "acme"])


def test_log_and_entry_list(isolated_config):
    _setup(isolated_config)
    result = runner.invoke(app, ["log", "9am to 11:30am", "--project", "api", "--note", "standup"])
    assert result.exit_code == 0, result.output
    assert "2:30" in result.output

    result = runner.invoke(app, ["entry", "list"])
    assert result.exit_code == 0
    assert "acme/api" in result.output
    assert "standup" in result.output
    assert "Total" in result.output


def test_log_uses_default_project_from_config(isolated_config):
    _setup(isolated_config)
    runner.invoke(app, ["config", "set", "defaults.project", "api", "--local"])
    result = runner.invoke(app, ["log", "2h"])
    assert result.exit_code == 0, result.output


def test_log_without_project_errors(isolated_config):
    _setup(isolated_config)
    result = runner.invoke(app, ["log", "2h"])
    assert result.exit_code == 1
    assert "--project" in result.output


def test_log_ambiguous_spec_shows_candidates(isolated_config):
    _setup(isolated_config)
    result = runner.invoke(app, ["log", "6 to 8", "--project", "api"])
    assert result.exit_code == 1
    assert "ambiguous" in result.output.lower()
    assert "am/pm" in result.output


def test_log_overlap_aborts_non_interactive(isolated_config):
    _setup(isolated_config)
    assert runner.invoke(app, ["log", "9-11", "-p", "api"]).exit_code == 0
    result = runner.invoke(app, ["log", "10-12", "-p", "api"])
    assert result.exit_code == 1
    assert "Overlaps" in result.output
    # --force logs it
    assert runner.invoke(app, ["log", "10-12", "-p", "api", "--force"]).exit_code == 0


def test_timer_lifecycle(isolated_config):
    _setup(isolated_config)
    # "midnight" is the only --at that's in the past at any time of day;
    # a clock time like "9am" would be rejected as future when run earlier
    result = runner.invoke(app, ["start", "api", "--at", "midnight", "--note", "pairing"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "acme/api" in result.output
    assert "pairing" in result.output

    result = runner.invoke(app, ["stop", "--at", "12:30am"])
    assert result.exit_code == 0
    assert "0:30" in result.output

    result = runner.invoke(app, ["status"])
    assert "No timer running" in result.output
    assert "0:30" in result.output


def test_timer_cancel(isolated_config):
    _setup(isolated_config)
    runner.invoke(app, ["start", "api"])
    result = runner.invoke(app, ["cancel"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["entry", "list"])
    assert "No entries" in result.output


def test_entry_edit_and_rm(isolated_config):
    _setup(isolated_config)
    runner.invoke(app, ["log", "1h", "-p", "api"])
    listing = runner.invoke(app, ["entry", "list"]).output
    uid = listing.splitlines()[2].split()[0]  # first data row, ID column

    result = runner.invoke(app, ["entry", "edit", uid, "--time", "9-11:30", "--note", "x"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["entry", "rm", uid])
    assert result.exit_code == 0
    assert "No entries" in runner.invoke(app, ["entry", "list"]).output


def test_entry_list_json(isolated_config):
    _setup(isolated_config)
    runner.invoke(app, ["log", "yesterday 2h", "-p", "api"])
    result = runner.invoke(app, ["entry", "list", "--json"])
    assert result.exit_code == 0
    assert '"seconds": 7200' in result.output
