"""Tests for TUI data helpers that expose expense data."""

from datetime import date
from decimal import Decimal
from typing import ClassVar

from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import projects as project_svc
from ttd.tui import _data


async def test_recent_expense_choices(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    suggestions = await _data.recent_expense_suggestions(project_slug="api-rewrite")
    assert [(s.description, s.amount) for s in suggestions] == [("Claude Code", Decimal("100"))]


async def test_recent_expense_suggestions_empty(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    suggestions = await _data.recent_expense_suggestions(project_slug="api-rewrite")
    assert suggestions == []


async def test_expenses_for_invoice_returns_expense_lines(db):
    """expenses_for_invoice is a thin accessor over view.expense_lines."""

    # Build a minimal fake view with expense_lines already set.
    class _FakeView:
        expense_lines: ClassVar = ["line-a", "line-b"]

    view = _FakeView()
    result = await _data.expenses_for_invoice(view)
    assert result == ["line-a", "line-b"]
