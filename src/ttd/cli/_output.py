"""Shared Rich console + table styling for CLI output."""

from rich.console import Console
from rich.table import Table
from rich.theme import Theme

ACCENT = "#ffb000"

console = Console(
    theme=Theme(
        {
            "accent": ACCENT,
            "muted": "grey58",
            "ok": "green",
            "warn": "yellow",
            "err": "bold red",
        }
    )
)
err_console = Console(stderr=True, style="bold red")


def table(*columns: str, title: str | None = None) -> Table:
    t = Table(
        title=title,
        header_style=f"bold {ACCENT}",
        border_style="grey35",
        title_style="bold",
        show_edge=False,
        pad_edge=False,
    )
    right_cols = (
        "rate",
        "hours",
        "amount",
        "total",
        "seconds",
        "income",
        "set aside",
        "remitted",
        "balance",
        "est. tax",
        "take-home",
    )
    for col in columns:
        t.add_column(col, justify="right" if col.lower() in right_cols else "left")
    return t


def success(message: str) -> None:
    console.print(f"[ok]✓[/ok] {message}")


def warn(message: str) -> None:
    console.print(f"[warn]![/warn] {message}")


def error(message: str) -> None:
    err_console.print(f"✗ {message}")
