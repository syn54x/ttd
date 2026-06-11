"""`ttd config …` commands."""

import os
import subprocess
from typing import Annotated

from cyclopts import Parameter

from ttd.cli._output import console, error, success, table
from ttd.cli._run import TtdApp
from ttd.config import loader, writer
from ttd.core.errors import TtdError

app = TtdApp(name="config", help="Read and write configuration.")

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
    """List effective configuration."""
    cfg = loader.load_config()
    values = _flatten(cfg.settings.model_dump(mode="json"))
    cols = ("Key", "Value", "Origin") if origin else ("Key", "Value")
    t = table(*cols)
    for key in sorted(values):
        value = values[key]
        rendered = "[muted]unset[/muted]" if value is None else str(value)
        if origin:
            t.add_row(key, rendered, cfg.provenance.get(key, "default"))
        else:
            t.add_row(key, rendered)
    console.print(t)


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
