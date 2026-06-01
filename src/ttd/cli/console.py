"""Shared Rich console for CLI output."""

from __future__ import annotations

from rich.console import Console, RenderableType

stdout = Console()
stderr = Console(stderr=True)


def success(message: str) -> None:
    """Print a success line to stdout."""
    stdout.print(f"[green]✓[/green] {message}")


def info(message: RenderableType) -> None:
    """Print neutral informational output (text or Rich renderables)."""
    stdout.print(message)


def muted(message: str) -> None:
    """Print dim placeholder text (e.g. empty lists)."""
    stdout.print(f"[dim]{message}[/dim]")


def error(message: str) -> None:
    """Print an error line to stderr."""
    stderr.print(f"[bold red]Error:[/bold red] {message}")
