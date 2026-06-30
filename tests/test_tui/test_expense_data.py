"""Tests for TUI data helpers that expose expense data."""

from datetime import date
from decimal import Decimal
from typing import ClassVar

from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import projects as project_svc
from ttd.tui import _data
from ttd.tui.screens._base import _validate_amount, _validate_date


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


# ---------------------------------------------------------------------------
# add_expense_entry
# ---------------------------------------------------------------------------


async def test_add_expense_entry_with_date(db):
    """add_expense_entry creates an expense with the correct fields."""
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")

    expense = await _data.add_expense_entry(
        {
            "project": "acme-corp/api-rewrite",
            "description": "Claude",
            "amount": "100",
            "date": "2026-06-15",
        }
    )

    assert expense.description == "Claude"
    assert expense.amount == Decimal("100")
    assert expense.incurred_date == date(2026, 6, 15)


async def test_add_expense_entry_blank_date_defaults_to_today(db):
    """Blank / absent date key means incurred today."""
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")

    expense = await _data.add_expense_entry(
        {
            "project": "acme-corp/api-rewrite",
            "description": "Figma",
            "amount": "15.50",
            # no "date" key → should default to today
        }
    )

    assert expense.incurred_date == date.today()


async def test_add_expense_entry_missing_date_key_defaults_to_today(db):
    """Explicitly blank date string also defaults to today."""
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")

    expense = await _data.add_expense_entry(
        {
            "project": "acme-corp/api-rewrite",
            "description": "Software",
            "amount": "9.99",
            "date": "",
        }
    )

    assert expense.incurred_date == date.today()


# ---------------------------------------------------------------------------
# _validate_amount (pure function — no DB needed)
# ---------------------------------------------------------------------------


def test_validate_amount_valid():
    assert _validate_amount("100.00") is True
    assert _validate_amount("0.01") is True
    assert _validate_amount("1") is True


def test_validate_amount_zero():
    result = _validate_amount("0")
    assert result is not True
    assert "positive" in result


def test_validate_amount_negative():
    result = _validate_amount("-5")
    assert result is not True
    assert "positive" in result


def test_validate_amount_non_numeric():
    result = _validate_amount("abc")
    assert result is not True
    assert "number" in result


# ---------------------------------------------------------------------------
# _validate_date (pure function — no DB needed)
# ---------------------------------------------------------------------------


def test_validate_date_valid():
    assert _validate_date("2026-06-15") is True
    assert _validate_date("2024-01-01") is True


def test_validate_date_invalid():
    result = _validate_date("not-a-date")
    assert result is not True
    assert "YYYY-MM-DD" in result


def test_validate_date_bad_format():
    result = _validate_date("15/06/2026")
    assert result is not True
    assert "YYYY-MM-DD" in result
