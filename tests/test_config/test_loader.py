from decimal import Decimal
from pathlib import Path

import pytest

from ttd.config.loader import find_local_config, global_config_path, load_config
from ttd.core.errors import ConfigError


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {"TTD_CONFIG_DIR": str(tmp_path / "global"), **extra}


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_defaults_when_no_files(tmp_path):
    cfg = load_config(start=tmp_path, env=_env(tmp_path))
    assert cfg.settings.business.currency == "USD"
    assert cfg.settings.billing.increment_minutes == 15
    assert cfg.provenance == {}
    assert cfg.local_path is None


def test_global_config_applies(tmp_path):
    write(
        tmp_path / "global" / "config.toml",
        "[business]\ncurrency = 'EUR'\ndefault_hourly_rate = 120.5\n",
    )
    cfg = load_config(start=tmp_path, env=_env(tmp_path))
    assert cfg.settings.business.currency == "EUR"
    assert cfg.settings.business.default_hourly_rate == Decimal("120.5")
    assert cfg.provenance["business.currency"] == "global"


def test_local_overrides_global_and_walks_up(tmp_path):
    write(tmp_path / "global" / "config.toml", "[business]\ncurrency = 'EUR'\n")
    write(
        tmp_path / "repo" / ".ttd.toml",
        "[business]\ncurrency = 'GBP'\n[defaults]\nclient = 'acme'\n",
    )
    nested = tmp_path / "repo" / "src" / "deep"
    nested.mkdir(parents=True)
    cfg = load_config(start=nested, env=_env(tmp_path))
    assert cfg.settings.business.currency == "GBP"
    assert cfg.settings.defaults.client == "acme"
    assert cfg.provenance["business.currency"] == "local"
    assert cfg.local_path == tmp_path / "repo" / ".ttd.toml"


def test_nearest_local_wins(tmp_path):
    write(tmp_path / "outer" / ".ttd.toml", "[defaults]\nclient = 'outer'\n")
    write(tmp_path / "outer" / "inner" / ".ttd.toml", "[defaults]\nclient = 'inner'\n")
    cfg = load_config(start=tmp_path / "outer" / "inner", env=_env(tmp_path))
    assert cfg.settings.defaults.client == "inner"


def test_env_overrides_local(tmp_path):
    write(tmp_path / "repo" / ".ttd.toml", "[business]\ncurrency = 'GBP'\n")
    env = _env(tmp_path, TTD_BUSINESS__CURRENCY="CAD")
    cfg = load_config(start=tmp_path / "repo", env=env)
    assert cfg.settings.business.currency == "CAD"
    assert cfg.provenance["business.currency"] == "env"


def test_ttd_db_path_env(tmp_path):
    env = _env(tmp_path, TTD_DB_PATH=str(tmp_path / "custom.db"))
    cfg = load_config(start=tmp_path, env=env)
    assert cfg.settings.db_path == tmp_path / "custom.db"


def test_invalid_value_raises_config_error(tmp_path):
    write(tmp_path / "global" / "config.toml", "[billing]\nrounding = 'sideways'\n")
    with pytest.raises(ConfigError, match=r"billing\.rounding"):
        load_config(start=tmp_path, env=_env(tmp_path))


def test_unknown_key_rejected(tmp_path):
    write(tmp_path / "global" / "config.toml", "[billing]\nrunding = 'up'\n")
    with pytest.raises(ConfigError):
        load_config(start=tmp_path, env=_env(tmp_path))


def test_invalid_toml_raises(tmp_path):
    write(tmp_path / "global" / "config.toml", "not toml ===")
    with pytest.raises(ConfigError, match="Invalid TOML"):
        load_config(start=tmp_path, env=_env(tmp_path))


def test_global_path_resolution_order(tmp_path):
    assert global_config_path({"TTD_CONFIG_DIR": "/x"}) == Path("/x/config.toml")
    assert global_config_path({"XDG_CONFIG_HOME": "/y"}) == Path("/y/ttd/config.toml")
    assert global_config_path({}) == Path.home() / ".config" / "ttd" / "config.toml"


def test_discovery_stops_at_home(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    work = fake_home / "projects" / "thing"
    work.mkdir(parents=True)
    write(tmp_path / ".ttd.toml", "[defaults]\nclient = 'above-home'\n")  # above $HOME
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert find_local_config(work) is None


def test_invoice_output_dir_default_is_expanded(tmp_path):
    # pydantic skips validators on defaults unless validate_default is set;
    # an unexpanded default once created a literal "~" directory in cwd
    cfg = load_config(start=tmp_path, env=_env(tmp_path))
    out = cfg.settings.invoice.output_dir
    assert out.is_absolute()
    assert "~" not in out.parts


def test_invoice_output_dir_configured_tilde_expands(tmp_path):
    write(tmp_path / "global" / "config.toml", "[invoice]\noutput_dir = '~/custom/place'\n")
    cfg = load_config(start=tmp_path, env=_env(tmp_path))
    assert cfg.settings.invoice.output_dir == Path.home() / "custom" / "place"
