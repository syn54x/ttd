# Flexible Invoice Periods Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept richer invoice period specs (relative durations, month-name ranges) and record each invoice's period from the items actually billed rather than the requested window.

**Architecture:** Extend `reporting/periods.py:parse_period` with two self-contained matchers (relative durations; month-name ranges with a closest-year rule). Separately, make `services/invoicing.py` derive the stored invoice period from the billed line dates. No new dependencies; no schema change.

**Tech Stack:** Python 3.13, stdlib `re`/`calendar`/`datetime`, Ferro-ORM/SQLite, pytest + pytest-asyncio.

## Global Constraints

- All new parsing lives in `reporting/periods.py`. Do NOT reuse/extend the `ttd log` grammar and do NOT add an NL-date dependency.
- **Relative forms:** `this week`/`last week` (calendar, respect `display.week_start`); rolling `last <N> days|weeks|months` ending **today**; `<N>` is a digit or a word `one`…`twelve`.
- **Month-name forms:** full names + 3-letter abbreviations; separators `to`/`through`/`thru`/`until`/`till`/`-`/`–`/`—`/`..`; shorthands `<month>` (whole month) and `<month> <day> <sep> <day>` (second inherits month); optional single trailing 4-digit year applies to both endpoints.
- **Year inference (closest-year, never future):** candidates = this year and last year; pick the one whose range is temporally closest to today (0 if today inside); ties → this year; never infer next year. Cross-year wrap: when the end month < start month, the end year = start year + 1.
- **Derived invoice period:** the parsed `Period` is only a sieve; the invoice's `period_start`/`period_end` = min–max of billed line dates (`work_date` for time, `incurred_date` for expenses). Refresh re-derives.
- Coverage gate `fail_under = 84` stays green; `ty` + `ruff` clean; avoid non-ASCII in code literals that trips `RUF001`.
- Tests: `asyncio_mode = "auto"`. Parser tests are pure (no db). Behavioral invoicing tests use the `db` fixture; set up via `client_svc.create_client`, `project_svc.create_project`, `entry_svc.log_entry`, `expense_svc.add_expense`.

## File Structure

- **Modify:** `src/ttd/reporting/periods.py` — the two new matchers + `parse_period` wiring + error text (Tasks 1–2).
- **Modify:** `src/ttd/cli/invoices.py` — pass `week_start` to `parse_period`; update `--period` help (Tasks 1–2).
- **Modify:** `src/ttd/tui/screens/invoices.py` — pass `week_start`; update the period placeholder/label (Tasks 1–2).
- **Modify:** `src/ttd/services/invoicing.py` — derive period in `build_draft` + `apply_refresh` (Task 3).
- **Create:** `tests/test_reporting/test_periods.py` — parser unit tests (Tasks 1–2).
- **Create:** `tests/test_invoicing/test_derived_period.py` — behavioral period-derivation tests (Task 3).

---

## Task 1: Relative-duration parsing

**Files:**
- Modify: `src/ttd/reporting/periods.py`
- Modify: `src/ttd/cli/invoices.py`, `src/ttd/tui/screens/invoices.py`
- Test: `tests/test_reporting/test_periods.py`

**Interfaces:**
- Produces: `parse_period(text: str, today: date, *, week_start: str = "monday") -> Period` — new keyword `week_start`; new accepted forms `this week`, `last week`, and `last <N> days|weeks|months`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reporting/test_periods.py
from datetime import date

from ttd.reporting import periods


def test_this_week_and_last_week():
    today = date(2026, 6, 18)  # a Thursday
    tw = periods.parse_period("this week", today)
    assert tw.start == date(2026, 6, 15) and tw.end == date(2026, 6, 21)  # Mon–Sun
    lw = periods.parse_period("last week", today)
    assert lw.start == date(2026, 6, 8) and lw.end == date(2026, 6, 14)


def test_rolling_last_n_ending_today():
    today = date(2026, 6, 18)
    assert periods.parse_period("last two weeks", today).start == date(2026, 6, 5)
    assert periods.parse_period("last two weeks", today).end == today
    assert periods.parse_period("last 10 days", today).start == date(2026, 6, 9)
    assert periods.parse_period("last 1 week", today).start == date(2026, 6, 12)
    assert periods.parse_period("last 3 months", today).start == date(2026, 3, 18)
    assert periods.parse_period("last 3 months", today).end == today


def test_rolling_month_clamps_day():
    # today Mar 31 minus 1 month clamps to Feb 28 (2026 not a leap year)
    assert periods.parse_period("last 1 month", date(2026, 3, 31)).start == date(2026, 2, 28)


def test_week_start_sunday():
    today = date(2026, 6, 18)
    tw = periods.parse_period("this week", today, week_start="sunday")
    assert tw.start == date(2026, 6, 14)  # Sunday
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reporting/test_periods.py -v`
Expected: FAIL — `parse_period` raises `TtdError("Can't read period 'this week' …")` / rejects the rolling forms.

- [ ] **Step 3: Add the relative matcher + wire `parse_period`**

In `src/ttd/reporting/periods.py`, add near the other module constants:

```python
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_RELATIVE_RE = re.compile(r"^last\s+(\w+)\s+(day|days|week|weeks|month|months)$")


def _subtract_months(d: date, n: int) -> date:
    """d shifted back n calendar months, clamping the day to the target month."""
    month_index = (d.year * 12 + (d.month - 1)) - n
    year, month = divmod(month_index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _parse_relative(text: str, today: date) -> Period | None:
    """Rolling 'last <N> days|weeks|months' ending today; None if no match."""
    m = _RELATIVE_RE.match(text)
    if m is None:
        return None
    raw, unit = m[1], m[2].rstrip("s")
    n = _NUMBER_WORDS.get(raw) or (int(raw) if raw.isdigit() else 0)
    if n < 1:
        raise TtdError(f"'{text}' — the count must be a positive number")
    if unit == "day":
        start = today - timedelta(days=n - 1)
    elif unit == "week":
        start = today - timedelta(days=n * 7 - 1)
    else:  # month
        start = _subtract_months(today, n)
    return range_period(start, today)
```

Rewrite `parse_period` to take `week_start` and handle the new week/relative forms:

```python
def parse_period(text: str, today: date, *, week_start: str = "monday") -> Period:
    """Parse a human period spec. Supports: '' / 'last month' / 'this month' /
    'this week' / 'last week' / 'last <N> days|weeks|months' / 'YYYY-MM' /
    'YYYY-MM-DD to YYYY-MM-DD' / month-name ranges like 'june 16 to june 30'."""
    text = text.strip().lower()
    if text in ("", "last month"):
        return month_period(today, last=True)
    if text == "this month":
        return month_period(today)
    if text == "this week":
        return week_period(today, week_start)
    if text == "last week":
        return week_period(today, week_start, last=True)
    if _MONTH_RE.match(text):
        return month_period(today, ym=text)
    if m := _RANGE_RE.match(text):
        try:
            return range_period(date.fromisoformat(m[1]), date.fromisoformat(m[2]))
        except ValueError as exc:
            raise TtdError(f"Not a real date in '{text}' ({exc})") from exc
    if relative := _parse_relative(text, today):
        return relative
    raise TtdError(
        f"Can't read period '{text}' — try '2026-05', 'last month', 'this week', "
        "'last two weeks', or '2026-05-01 to 2026-05-15'"
    )
```

(The month-name branch is added in Task 2, immediately before the final `raise`.)

- [ ] **Step 4: Pass `week_start` from the invoice call sites**

In `src/ttd/cli/invoices.py`, `_resolve_period` calls `periods.parse_period(period, datetime.now().date())` — change to:

```python
        return periods.parse_period(
            period, datetime.now().date(), week_start=get_settings().display.week_start
        )
```

In `src/ttd/tui/screens/invoices.py`, `_rebuild` calls `periods.parse_period(raw, datetime.now().date())` — change to:

```python
        period = periods.parse_period(
            raw, datetime.now().date(), week_start=get_settings().display.week_start
        )
```

(Both modules already import `get_settings`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reporting/test_periods.py -v && uv run pytest -q && uv run ty check && uv run ruff check`
Expected: PASS, full suite green (coverage ≥84%), clean.

- [ ] **Step 6: Commit**

```bash
git add src/ttd/reporting/periods.py src/ttd/cli/invoices.py src/ttd/tui/screens/invoices.py tests/test_reporting/test_periods.py
git commit -m "feat: relative period specs (this/last week, last N days/weeks/months)"
```

---

## Task 2: Month-name ranges + closest-year + help text

**Files:**
- Modify: `src/ttd/reporting/periods.py`
- Modify: `src/ttd/cli/invoices.py`, `src/ttd/tui/screens/invoices.py`
- Test: `tests/test_reporting/test_periods.py` (append)

**Interfaces:**
- Consumes: `parse_period` (Task 1), `range_period`, `month_period`.
- Produces: `parse_period` additionally accepts `<month>`, `<month> <day> <sep> <month> <day>`, `<month> <day> <sep> <day>`, with optional trailing 4-digit year and the closest-year rule.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reporting/test_periods.py (append)
import pytest
from ttd.core.errors import TtdError


def test_month_name_range_closest_year():
    # today mid-2026
    today = date(2026, 7, 1)
    p = periods.parse_period("june 16 to june 30", today)
    assert p.start == date(2026, 6, 16) and p.end == date(2026, 6, 30)


def test_closest_year_examples():
    # Jan 1 2026, "dec 15 - dec 31" -> Dec 2025 (last year is closest)
    p = periods.parse_period("dec 15 - dec 31", date(2026, 1, 1))
    assert p.start == date(2025, 12, 15) and p.end == date(2025, 12, 31)
    # June 30 2026, "june 16 - june 30" -> this year (today inside)
    p = periods.parse_period("june 16 - june 30", date(2026, 6, 30))
    assert p.start == date(2026, 6, 16)
    # June 1 2026, "june 16 - june 30" -> this year (near future beats a year ago)
    p = periods.parse_period("june 16 - june 30", date(2026, 6, 1))
    assert p.start == date(2026, 6, 16)


def test_month_shorthands():
    today = date(2026, 7, 1)
    whole = periods.parse_period("june", today)
    assert whole.start == date(2026, 6, 1) and whole.end == date(2026, 6, 30)
    inherit = periods.parse_period("june 16 - 30", today)
    assert inherit.start == date(2026, 6, 16) and inherit.end == date(2026, 6, 30)
    abbrev = periods.parse_period("jun 16 to jun 30", today)
    assert abbrev.start == date(2026, 6, 16)


def test_cross_year_wrap():
    # "dec 28 to jan 3" — end month wraps into the next year
    p = periods.parse_period("dec 28 to jan 3", date(2026, 1, 15))
    # closest-year for start Dec: Dec 2025 (ended ~2 weeks ago) beats Dec 2026
    assert p.start == date(2025, 12, 28) and p.end == date(2026, 1, 3)


def test_explicit_year_honored():
    p = periods.parse_period("june 16 to june 30 2024", date(2026, 7, 1))
    assert p.start == date(2024, 6, 16) and p.end == date(2024, 6, 30)


def test_bad_month_name_errors():
    with pytest.raises(TtdError):
        periods.parse_period("smarch 3 to smarch 9", date(2026, 7, 1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reporting/test_periods.py -k "month or closest or cross or explicit or shorthand or bad_month" -v`
Expected: FAIL — these forms hit the final `raise TtdError("Can't read period …")`.

- [ ] **Step 3: Add the month-name matcher + closest-year**

In `src/ttd/reporting/periods.py`, add constants and helpers:

```python
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MON = r"[a-z]{3,9}"
_SEP = r"(?:to|through|thru|until|till|\.\.|-|–|—)"
_MM_RANGE_RE = re.compile(
    rf"^(?P<m1>{_MON})\s+(?P<d1>\d{{1,2}})\s*{_SEP}\s*(?P<m2>{_MON})\s+(?P<d2>\d{{1,2}})"
    rf"(?:\s+(?P<year>\d{{4}}))?$"
)
_MD_RANGE_RE = re.compile(
    rf"^(?P<m1>{_MON})\s+(?P<d1>\d{{1,2}})\s*{_SEP}\s*(?P<d2>\d{{1,2}})"
    rf"(?:\s+(?P<year>\d{{4}}))?$"
)
_MONTH_ONLY_RE = re.compile(rf"^(?P<m1>{_MON})(?:\s+(?P<year>\d{{4}}))?$")


def _month_num(name: str) -> int | None:
    return _MONTHS.get(name)


def _range_distance(start: date, end: date, today: date) -> int:
    if start <= today <= end:
        return 0
    if today < start:
        return (start - today).days
    return (today - end).days


def _closest_year_range(m1: int, d1: int, m2: int, d2: int, today: date) -> Period:
    """Build (start, end) for the closest non-future year; end wraps to +1 year
    when the end month is earlier than the start month."""
    best: tuple[int, date, date] | None = None
    for y in (today.year, today.year - 1):  # this year first → ties favor it
        end_year = y + 1 if m2 < m1 else y
        try:
            start = date(y, m1, d1)
            end = date(end_year, m2, d2)
        except ValueError:
            continue
        dist = _range_distance(start, end, today)
        if best is None or dist < best[0]:
            best = (dist, start, end)
    if best is None:
        raise TtdError("Not a real date in that month-name range")
    return range_period(best[1], best[2])


def _fixed_year_range(m1: int, d1: int, m2: int, d2: int, year: int) -> Period:
    end_year = year + 1 if m2 < m1 else year
    try:
        return range_period(date(year, m1, d1), date(end_year, m2, d2))
    except ValueError as exc:
        raise TtdError(f"Not a real date ({exc})") from exc


def _parse_month_name(text: str, today: date) -> Period | None:
    # whole month: "june" / "june 2025"
    if m := _MONTH_ONLY_RE.match(text):
        num = _month_num(m["m1"])
        if num is None:
            return None
        year = int(m["year"]) if m["year"] else _closest_month_year(num, today)
        return month_period(date(year, num, 1), ym=f"{year}-{num:02d}")
    # month day <sep> month day
    if m := _MM_RANGE_RE.match(text):
        n1, n2 = _month_num(m["m1"]), _month_num(m["m2"])
        if n1 is None or n2 is None:
            return None
        d1, d2 = int(m["d1"]), int(m["d2"])
        if m["year"]:
            return _fixed_year_range(n1, d1, n2, d2, int(m["year"]))
        return _closest_year_range(n1, d1, n2, d2, today)
    # month day <sep> day  (inherit month)
    if m := _MD_RANGE_RE.match(text):
        n1 = _month_num(m["m1"])
        if n1 is None:
            return None
        d1, d2 = int(m["d1"]), int(m["d2"])
        if m["year"]:
            return _fixed_year_range(n1, d1, n1, d2, int(m["year"]))
        return _closest_year_range(n1, d1, n1, d2, today)
    return None


def _closest_month_year(month: int, today: date) -> int:
    """Closest non-future year for a whole-month reference."""
    best: tuple[int, int] | None = None
    for y in (today.year, today.year - 1):
        first = date(y, month, 1)
        last = date(y, month, calendar.monthrange(y, month)[1])
        dist = _range_distance(first, last, today)
        if best is None or dist < best[0]:
            best = (dist, y)
    assert best is not None
    return best[1]
```

> Note: `_MON` matches any 3–9 letter word, so `_parse_month_name` returns `None` (not a match) when the "month" isn't real (`_month_num` → None), letting `parse_period` fall through to its error. But a *range* with a bad month (e.g. `smarch 3 to smarch 9`) matches `_MM_RANGE_RE` yet `_month_num` is None → returns None → falls through to the final `TtdError`. Good.

Wire it into `parse_period` immediately before the final `raise`:

```python
    if relative := _parse_relative(text, today):
        return relative
    if month_name := _parse_month_name(text, today):
        return month_name
    raise TtdError(
        f"Can't read period '{text}' — try '2026-05', 'last month', 'this week', "
        "'last two weeks', 'june 16 to june 30', or '2026-05-01 to 2026-05-15'"
    )
```

- [ ] **Step 4: Update the CLI + TUI help text**

In `src/ttd/cli/invoices.py`, the `--period` `help=`:

```python
            help=(
                "Period spec: 'last month', 'this week', 'last two weeks', "
                "'june 16 to june 30', YYYY-MM, or YYYY-MM-DD to YYYY-MM-DD"
            )
```

In `src/ttd/tui/screens/invoices.py`, the period `Input` placeholder:

```python
                placeholder="last month · this week · last two weeks · june 16 to june 30 · 2026-05",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reporting/test_periods.py -v && uv run pytest -q && uv run ty check && uv run ruff check`
Expected: PASS, full suite green, clean.

- [ ] **Step 6: Commit**

```bash
git add src/ttd/reporting/periods.py src/ttd/cli/invoices.py src/ttd/tui/screens/invoices.py tests/test_reporting/test_periods.py
git commit -m "feat: month-name period ranges with closest-year inference"
```

---

## Task 3: Derive the invoice period from billed items

**Files:**
- Modify: `src/ttd/services/invoicing.py`
- Test: `tests/test_invoicing/test_derived_period.py`

**Interfaces:**
- Consumes: `build_draft`, `persist_draft`, `apply_refresh`, `Draft`, `DraftLine.work_date`, `DraftExpenseLine.incurred_date`, `range_period`, `InvoiceLine`, `InvoiceExpenseLine`.
- Produces: `Draft.period` = the derived (min–max billed-date) period; `apply_refresh` updates `invoice.period_start`/`period_end` from persisted rows.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_invoicing/test_derived_period.py
from datetime import date, datetime
from decimal import Decimal

from ttd.config.schema import Settings
from ttd.reporting import periods
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc


async def _setup(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")


def _june() -> periods.Period:
    return periods.range_period(date(2026, 6, 1), date(2026, 6, 30))


async def test_invoice_period_tightens_to_billed_entries(db):
    await _setup(db)
    from ttd.services import entries as entry_svc
    await entry_svc.log_entry("2026-06-16 9am-11am", "api-rewrite", now=datetime(2026, 6, 16, 12))
    await entry_svc.log_entry("2026-06-20 9am-10am", "api-rewrite", now=datetime(2026, 6, 20, 12))
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", _june(), settings), settings)
    assert invoice.period_start == date(2026, 6, 16)   # not June 1
    assert invoice.period_end == date(2026, 6, 20)     # not June 30


async def test_invoice_period_from_expenses_only(db):
    await _setup(db)
    await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 18))
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", _june(), settings), settings)
    assert invoice.period_start == date(2026, 6, 18)
    assert invoice.period_end == date(2026, 6, 18)


async def test_invoice_period_spans_time_and_expenses(db):
    await _setup(db)
    from ttd.services import entries as entry_svc
    await entry_svc.log_entry("2026-06-16 9am-11am", "api-rewrite", now=datetime(2026, 6, 16, 12))
    await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 25))
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", _june(), settings), settings)
    assert invoice.period_start == date(2026, 6, 16)
    assert invoice.period_end == date(2026, 6, 25)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_invoicing/test_derived_period.py -v`
Expected: FAIL — `period_start`/`period_end` are June 1 / June 30 (the requested window).

- [ ] **Step 3: Derive the period in `build_draft`**

In `src/ttd/services/invoicing.py`, add a helper near `_draft_totals`:

```python
def _derive_period(lines: list[DraftLine], expense_lines: list[DraftExpenseLine], fallback: Period) -> Period:
    dates = [li.work_date for li in lines] + [el.incurred_date for el in expense_lines]
    if not dates:
        return fallback
    return range_period(min(dates), max(dates))
```

(`range_period` is already imported from `ttd.reporting.periods`; if only `Period` is imported, add `range_period` to that import.)

In `build_draft`, change the final `return Draft(...)` to use the derived period:

```python
    subtotal, expenses_subtotal, tax, total = _draft_totals(
        lines, expense_lines, settings.invoice.tax_rate
    )
    actual_period = _derive_period(lines, expense_lines, fallback=period)
    return Draft(
        client=client,
        period=actual_period,
        lines=lines,
        expense_lines=expense_lines,
        subtotal=subtotal,
        expenses_subtotal=expenses_subtotal,
        tax=tax,
        total=total,
    )
```

The empty-check above (`if not entries and not expenses:`) is unchanged and still reports the requested `period.label`, so a no-match window still errors clearly.

- [ ] **Step 4: Re-derive the period on refresh**

In `apply_refresh`, in the non-paid branch where `invoice.subtotal`/`tax`/`total`/`expenses_subtotal` are assigned (around the `invoice.save()` call), re-derive from the persisted rows before saving:

```python
            time_rows = await InvoiceLine.where(lambda li: li.invoice_id == invoice.id).all()
            exp_rows = await InvoiceExpenseLine.where(lambda li: li.invoice_id == invoice.id).all()
            billed_dates = [li.work_date for li in time_rows] + [li.incurred_date for li in exp_rows]
            if billed_dates:
                invoice.period_start = min(billed_dates)
                invoice.period_end = max(billed_dates)
            invoice.subtotal = fresh.after_subtotal
            invoice.tax = fresh.after_tax
            invoice.expenses_subtotal = fresh.after_expenses_subtotal
            invoice.total = fresh.after_total
            await invoice.save()
```

(Place the query after the line/expense reconciliation writes so it reflects the final rows. Match the exact existing assignment block; only add the period-derivation lines.)

- [ ] **Step 5: Add a refresh test**

```python
# tests/test_invoicing/test_derived_period.py (append)
from ttd.storage.models import Expense


async def test_refresh_reduces_period_when_item_removed(db):
    await _setup(db)
    from ttd.services import entries as entry_svc
    await entry_svc.log_entry("2026-06-16 9am-11am", "api-rewrite", now=datetime(2026, 6, 16, 12))
    exp = await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 25))
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", _june(), settings), settings)
    assert invoice.period_end == date(2026, 6, 25)
    # release + delete the later expense, then refresh
    locked = await Expense.get_or_none(exp.id)
    locked.invoice_id = None
    await locked.save()
    await locked.delete()
    preview = await svc.preview_refresh(invoice.number, settings)
    refreshed = await svc.apply_refresh(invoice.number, preview, settings)
    assert refreshed.period_end == date(2026, 6, 16)   # period tightened back to the entry
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_invoicing/test_derived_period.py -v && uv run pytest -q && uv run ty check && uv run ruff check`
Expected: PASS, full suite green (coverage ≥84%), clean. (Existing invoicing tests that assert on `period_start`/`period_end` may need updating if any asserted the full-window values — check `tests/test_services`/`tests/test_invoicing` for such assertions and update them to the derived values.)

- [ ] **Step 7: Commit**

```bash
git add src/ttd/services/invoicing.py tests/test_invoicing/test_derived_period.py
git commit -m "feat: record invoice period from billed items, not the requested window"
```

---

## Self-Review Notes (coverage against the spec)

- Part 1 relative durations (this/last week, rolling last N days/weeks/months, digit + word counts, week_start) → **Task 1**.
- Part 1 month-name ranges + shorthands (`june`, `june 16 - 30`, abbreviations, separators, optional trailing year) → **Task 2**.
- Part 2 closest-year (never future) + cross-year wrap → **Task 2** (`_closest_year_range`/`_closest_month_year`).
- Part 3 derived invoice period (build_draft + apply_refresh) → **Task 3**.
- Part 4 error/help text → error message in Tasks 1 & 2; CLI `--period` help + TUI placeholder in Task 2.
- Part 4 tests → parser tests (Tasks 1–2, `test_reporting/test_periods.py`), behavioral derivation tests (Task 3, `test_invoicing/test_derived_period.py`).
- **Deferred (per spec):** quarter/year-to-date/year forms; log-grammar reuse; report-specific changes (reports inherit the new forms for free via `parse_period`).
- **Type consistency:** `parse_period(text, today, *, week_start="monday")` is the one signature used by both new families and both call-site updates; `_derive_period(lines, expense_lines, fallback)` and the apply_refresh re-derivation both key on `work_date`/`incurred_date`.
- **Verify during impl:** confirm `range_period` is imported in `invoicing.py` (add to the `ttd.reporting.periods` import if only `Period` is there). Confirm no existing test asserts an invoice's period equals the full requested window (Task 3 Step 6 checks and updates any).
