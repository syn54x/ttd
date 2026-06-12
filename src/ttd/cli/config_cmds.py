"""`ttd config …` commands."""

import os
import subprocess
from typing import Annotated

from cyclopts import Parameter

from ttd.cli._output import console, error, success, table
from ttd.cli._run import TtdApp
from ttd.config import loader, writer
from ttd.config.schema import Settings
from ttd.core.errors import TtdError

app = TtdApp(
    name="config",
    help="""Read and write configuration.

ttd needs no setup: every option has a sensible built-in default, and config
files are created only when you first write to one. Settings you do change
are layered, highest precedence first:

1. `TTD_*` environment variables (`TTD_<SECTION>__<KEY>`, e.g. `TTD_BILLING__ROUNDING=up`)
2. The nearest `.ttd.toml`, walking up from the current directory — per-project overrides
3. The global config file (usually `~/.config/ttd/config.toml`) — your personal defaults
4. Built-in defaults

`config set` writes to the global file, or to `.ttd.toml` with `--local`.
`config list` shows every available option; add `--origin` to see which
layer set each value. `config path` shows where the files live.
""",
)

LocalOpt = Annotated[bool, Parameter(help="Target .ttd.toml in this directory")]


def _flatten(data: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{dotted}."))
        else:
            out[dotted] = value
    return out


def _descriptions() -> dict[str, str]:
    """Dotted key -> field description, from the Settings schema."""
    out: dict[str, str] = {}
    for section, section_field in Settings.model_fields.items():
        for key, f in section_field.annotation.model_fields.items():
            out[f"{section}.{key}"] = f.description or ""
    return out


@app.command(name="get")
def get(key: Annotated[str, Parameter(help="Dotted key, e.g. billing.rounding")]) -> None:
    """Print one config value."""
    cfg = loader.load_config()
    values = _flatten(cfg.settings.model_dump(mode="json"))
    if key not in values:
        error(f"Unknown config key '{key}'")
        raise SystemExit(1)
    console.print(values[key] if values[key] is not None else "[muted]unset[/muted]")


@app.command(name="set")
def set_(
    key: str,
    value: str,
    *,
    local: LocalOpt = False,
) -> None:
    """Set a config value (global by default, --local for .ttd.toml here)."""
    try:
        path = writer.set_value(key, value, local)
    except TtdError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    success(f"Set {key} = {value} in {path}")


@app.command(name="unset")
def unset(
    key: str,
    *,
    local: LocalOpt = False,
) -> None:
    """Remove a key from a config file."""
    try:
        path = writer.unset_value(key, local)
    except TtdError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    success(f"Unset {key} in {path}")


@app.command(name="list")
def list_(
    *,
    origin: Annotated[bool, Parameter(help="Show which layer set each key")] = False,
) -> None:
    """List every available option with its effective value."""
    cfg = loader.load_config()
    values = _flatten(cfg.settings.model_dump(mode="json"))
    descriptions = _descriptions()
    cols = ("Key", "Value", "Origin", "Description") if origin else ("Key", "Value", "Description")
    t = table(*cols)
    t.columns[0].overflow = "fold"  # keys must stay copyable for `config set`
    for key in sorted(values):
        value = values[key]
        rendered = "[muted]unset[/muted]" if value is None else str(value)
        desc = f"[muted]{descriptions.get(key, '')}[/muted]"
        if origin:
            t.add_row(key, rendered, cfg.provenance.get(key, "default"), desc)
        else:
            t.add_row(key, rendered, desc)
    console.print(t)
    console.print(
        "\n[muted]Every option is shown; values come from built-in defaults unless a config"
        " file or TTD_* env var overrides them"
        + ("" if origin else " (--origin shows which)")
        + ".\nChange one with `ttd config set <key> <value>` (--local for this directory's"
        " .ttd.toml); `ttd config -h` explains layering.[/muted]"
    )


@app.command(name="path")
def path() -> None:
    """Show config file paths (global and discovered local)."""
    cfg = loader.load_config()
    exists = "" if cfg.global_path.is_file() else " [muted](not created yet)[/muted]"
    console.print(f"global: {cfg.global_path}{exists}")
    console.print(f"local:  {cfg.local_path or '[muted]none found[/muted]'}")


@app.command(name="edit")
def edit(*, local: LocalOpt = False) -> None:
    """Open a config file in $EDITOR."""
    cfg = loader.load_config()
    target = (cfg.local_path or writer.target_path(local=True)) if local else cfg.global_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(target)], check=False)
