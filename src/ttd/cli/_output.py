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
    for col in columns:
        justify = (
            "right" if col.lower() in ("rate", "hours", "amount", "total", "seconds") else "left"
        )
        t.add_column(col, justify=justify)
    return t


def success(message: str) -> None:
    console.print(f"[ok]✓[/ok] {message}")


def warn(message: str) -> None:
    console.print(f"[warn]![/warn] {message}")


def error(message: str) -> None:
    err_console.print(f"✗ {message}")
