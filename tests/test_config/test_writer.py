import pytest

from ttd.config import writer
from ttd.core.errors import ConfigError


def test_set_creates_global_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TTD_CONFIG_DIR", str(tmp_path / "g"))
    path = writer.set_value("billing.increment_minutes", "6", local=False)
    assert path == tmp_path / "g" / "config.toml"
    assert "increment_minutes = 6" in path.read_text()


def test_set_local_writes_cwd_file(tmp_path):
    path = writer.set_value("defaults.client", "acme", local=True, start=tmp_path)
    assert path == tmp_path / ".ttd.toml"
    assert 'client = "acme"' in path.read_text()


def test_set_preserves_existing_content_and_comments(tmp_path):
    target = tmp_path / ".ttd.toml"
    target.write_text("# my settings\n[defaults]\nclient = 'acme' # pinned\n")
    writer.set_value("defaults.project", "api", local=True, start=tmp_path)
    text = target.read_text()
    assert "# my settings" in text
    assert "# pinned" in text
    assert 'project = "api"' in text


def test_set_rejects_unknown_key(tmp_path):
    with pytest.raises(ConfigError, match="Unknown config key"):
        writer.set_value("billing.bogus", "1", local=True, start=tmp_path)


def test_set_rejects_invalid_value(tmp_path):
    with pytest.raises(ConfigError, match="Invalid value"):
        writer.set_value("billing.rounding", "sideways", local=True, start=tmp_path)


def test_unset_removes_key_and_empty_section(tmp_path):
    writer.set_value("defaults.client", "acme", local=True, start=tmp_path)
    writer.unset_value("defaults.client", local=True, start=tmp_path)
    text = (tmp_path / ".ttd.toml").read_text()
    assert "client" not in text
    assert "[defaults]" not in text


def test_unset_missing_key_errors(tmp_path):
    writer.set_value("defaults.client", "acme", local=True, start=tmp_path)
    with pytest.raises(ConfigError, match="not set"):
        writer.unset_value("defaults.project", local=True, start=tmp_path)
