"""Round-trip fidelity: export → import into empty DB → export → identical."""

import pytest

from _runner import CliRunner
from ttd.cli.app import app

runner = CliRunner()


def _seed():
    runner.invoke(app, ["client", "add", "Acme Corp", "--rate", "150"])
    runner.invoke(app, ["client", "add", "Beta LLC", "--rate", "95", "--currency", "EUR"])
    runner.invoke(app, ["project", "add", "API", "--client", "acme-corp"])
    runner.invoke(app, ["project", "add", "Design", "--client", "beta-llc", "--rate", "120"])
    runner.invoke(app, ["log", "yesterday 9am to 12:30pm", "-p", "api", "--note", "auth, sessions"])
    runner.invoke(app, ["log", "yesterday 1pm to 3pm", "-p", "design", "--tags", "ui,review"])
    runner.invoke(app, ["log", "2h", "-p", "api", "--no-billable", "--note", 'quoted "stuff"'])


def _wipe_db(tmp_path, monkeypatch, name):
    monkeypatch.setenv("TTD_DB_PATH", str(tmp_path / name))


@pytest.mark.parametrize("ext", ["csv", "json", "xlsx", "numbers"])
def test_roundtrip(isolated_config, monkeypatch, ext):
    _seed()
    first = isolated_config / f"out1.{ext}"
    second = isolated_config / f"out2.{ext}"

    result = runner.invoke(app, ["export", str(first)])
    assert result.exit_code == 0, result.output
    assert "Exported 3" in result.output

    # fresh, empty DB
    _wipe_db(isolated_config, monkeypatch, f"second-{ext}.db")
    result = runner.invoke(app, ["import", str(first), "--create-missing"])
    assert result.exit_code == 0, result.output
    assert "Imported 3" in result.output

    result = runner.invoke(app, ["export", str(second)])
    assert result.exit_code == 0, result.output

    if ext in ("csv", "json"):
        assert first.read_text() == second.read_text(), "byte-identical round trip"
    else:
        # binary formats: compare canonical CSV of both DBs
        export1 = runner.invoke(app, ["export", str(isolated_config / f"chk-{ext}-b.csv")])
        assert export1.exit_code == 0
        _wipe_db(isolated_config, monkeypatch, f"third-{ext}.db")
        result = runner.invoke(app, ["import", str(second), "--create-missing"])
        assert result.exit_code == 0, result.output
        export2 = runner.invoke(app, ["export", str(isolated_config / f"chk-{ext}-c.csv")])
        assert export2.exit_code == 0
        a = (isolated_config / f"chk-{ext}-b.csv").read_text()
        c = (isolated_config / f"chk-{ext}-c.csv").read_text()
        assert a == c


def test_reimport_into_same_db_skips_everything(isolated_config):
    _seed()
    out = isolated_config / "out.csv"
    runner.invoke(app, ["export", str(out)])
    result = runner.invoke(app, ["import", str(out)])
    assert result.exit_code == 0, result.output
    assert "Imported 0" in result.output
    assert "already exists" in result.output


def test_json_carries_rates(isolated_config):
    _seed()
    out = isolated_config / "backup.json"
    runner.invoke(app, ["export", str(out)])
    text = out.read_text()
    assert '"hourly_rate": "150"' in text
    assert '"currency": "EUR"' in text
