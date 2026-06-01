---
title: Layered TOML config with pydantic-settings and pytest isolation
date: 2026-05-29
category: architecture-patterns
module: ttd.core.config
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - "Adding file-backed Settings layers (TOML, YAML) with pydantic-settings v2"
  - "Pytest uses Settings(data_dir=tmp_path) but tests hit the developer's real database"
  - "Implementing ttd config show|get|set|init against layered config files"
tags:
  - pydantic-settings
  - toml-config
  - pytest-isolation
  - ttd-config
  - questionary
related_components:
  - ttd.cli.config_cmds
  - tests.conftest
---

# Layered TOML config with pydantic-settings and pytest isolation

## Context

TTD M4 added machine configuration outside SQLite: global `{XDG_CONFIG_HOME}/ttd/ttd.toml`, optional local `ttd.toml` discovered by walking up from cwd, and `TTD_*` env overrides. Core exposes `get_settings()` (cached), `ttd config show|get|set|init`, and `init_config()` for the interactive wizard.

After shipping, the full pytest suite failed on machines with a real global config file because tests still constructed `Settings(data_dir=tmp_path)` in fixtures — but pydantic-settings loaded the developer's TOML first and overrode `data_dir` with `~/.local/share/ttd`. Symptoms looked like schema drift (`rounding_increment_minutes` column missing) because tests were writing to an old dogfood database, not the isolated tmp DB.

(session history) Prior sessions on branch `feat/tui-charm-m3` planned M4 as config-infra-only (defer timezone consumption), implemented layered TOML, added `config init`, briefly added a searchable timezone select, then removed timezone from v1 keys per product decision.

## Guidance

### Layer design (core, not CLI)

- **Paths:** `global_config_path()` → `{XDG_CONFIG_HOME}/ttd/ttd.toml`; `find_local_config()` walks cwd → filesystem root; `local_config_write_path()` returns nearest existing local file or `cwd/ttd.toml`.
- **Precedence (highest first):** `TTD_*` env (and cwd `.env`) → local TOML → global TOML → field defaults. Implement with `settings_customise_sources` returning `(env_settings, dotenv_settings, local_source, global_source, init_settings)` — **first tuple entry wins** in pydantic-settings v2.
- **Missing local file:** Point `TomlConfigSettingsSource` at a non-existent path under the global config parent (e.g. `.missing-local.toml`); missing files are ignored cleanly.
- **v1 keys:** `data_dir`, `db_filename`, `clock_format`. Legacy keys in existing files (e.g. removed `timezone`) are ignored via `extra="ignore"`.
- **Cache:** `@lru_cache` on `get_settings()`; call `clear_settings_cache()` after `config set` / `init_config`. Make `clear_settings_cache()` tolerant of monkeypatched `get_settings` (no `.cache_clear` on plain lambdas).
- **Mutation:** `set_config_value()` updates one key in target file; `init_config()` validates and writes all v1 keys. CLI stays thin.

### Pytest isolation (required when Settings loads real files)

Add an **autouse** fixture in `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def isolate_app_config(monkeypatch, tmp_path) -> None:
    xdg = tmp_path / "xdg-config"
    xdg.mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    for var in ("TTD_DATA_DIR", "TTD_DB_FILENAME", "TTD_CLOCK_FORMAT"):
        monkeypatch.delenv(var, raising=False)
    clear_settings_cache()
    yield
    clear_settings_cache()
```

**Why:** With TOML sources ranked above `init_settings`, `Settings(data_dir=tmp_path)` in the `settings` fixture does **not** win if a real global `ttd.toml` exists. Empty isolated XDG config lets constructor kwargs apply.

**Also keep** per-test `monkeypatch.setattr("ttd.core.config.get_settings", lambda: settings)` for CLI tests that bypass file load entirely.

Config-specific tests that set `XDG_CONFIG_HOME` again should use `mkdir(exist_ok=True)` to avoid clashing with the autouse fixture.

### questionary search filter

If `ask_select(..., use_search_filter=True)`, you **must** pass `use_jk_keys=False` to `questionary.select`. Otherwise:

`ValueError: Cannot use j/k keys with prefix filter search`

Wrap in `prompts.ask_select` so callers do not forget. (Timezone select was removed from `config init`; pattern remains for future long lists.)

## Why This Matters

Without autouse isolation, CI and pre-commit hooks pass only on clean machines; developers who ran `ttd config init` get dozens of false failures and may misdiagnose ORM/schema bugs. Without core-layered load, CLI and `init_db()` would diverge on precedence. Documenting the init-vs-TOML priority explains why "I passed explicit tmp_path" still connected to production data.

## When to Apply

- Any new Settings field or config file layer — extend `CONFIG_KEYS`, validators, and `resolve_sources()` together.
- New test modules that call `get_settings()` or `init_db()` without injected `Settings` — rely on autouse isolation or explicit monkeypatch.
- New interactive prompts with type-to-filter lists — use extended `ask_select`, not raw questionary, and disable j/k navigation.

## Examples

**Precedence check (manual):**

```bash
# global ttd.toml: data_dir = "/global"
# ./ttd.toml: data_dir = "./local"
# TTD_DATA_DIR=/env
ttd config get data_dir   # → /env
```

**Before (tests fail with global config on disk):**

```python
@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "ttd-data", db_filename="test.db")
# Still loads ~/.config/ttd/ttd.toml → dogfood DB → missing columns
```

**After:** autouse `isolate_app_config` + unchanged `settings` fixture → tmp DB only.

## Related

- Design reference: `docs/design/data-layer.md` (Configuration M4)
- Requirements: `brainstorms/2026-05-29-config-toml-requirements.md`
- Plan: `plans/2026-05-29-001-feat-config-toml-plan.md`
- Deferred: timezone/pendulum consumption — `brainstorms/2026-05-26-config-setup-requirements.md`
