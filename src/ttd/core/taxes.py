"""IRS estimated-tax quarters and set-aside math.

No tax law lives here — the set-aside rate is the user's own rule from
config. IRS estimated-tax quarters are not calendar quarters: Q2 covers two
months and Q4 covers four. Due dates are nominal (always the 15th) with no
weekend or holiday shifting.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ttd.core.errors import TtdError
from ttd.core.money import to_cents

# quarter -> ((start month, start day), (end month, end day)), both inclusive
_QUARTERS: dict[int, tuple[tuple[int, int], tuple[int, int]]] = {
    1: ((1, 1), (3, 31)),
    2: ((4, 1), (5, 31)),
    3: ((6, 1), (8, 31)),
    4: ((9, 1), (12, 31)),
}

# quarter -> (due month, due year offset); Q4 is due Jan 15 of the next year
_DUE: dict[int, tuple[int, int]] = {1: (4, 0), 2: (6, 0), 3: (9, 0), 4: (1, 1)}

_QUARTER_RE = re.compile(r"^(?:(\d{4})[ -]?)?q([1-4])$", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class TaxQuarter:
    """One IRS estimated-tax period within a year."""

    year: int
    quarter: int  # 1..4

    def __post_init__(self) -> None:
        if self.quarter not in _QUARTERS:
            raise TtdError(f"Quarter must be 1-4 (got {self.quarter})")

    @property
    def start(self) -> date:
        month, day = _QUARTERS[self.quarter][0]
        return date(self.year, month, day)

    @property
    def end(self) -> date:
        month, day = _QUARTERS[self.quarter][1]
        return date(self.year, month, day)

    @property
    def due_date(self) -> date:
        month, year_offset = _DUE[self.quarter]
        return date(self.year + year_offset, month, 15)

    @property
    def label(self) -> str:
        return f"{self.year}Q{self.quarter}"

    @classmethod
    def from_date(cls, d: date) -> "TaxQuarter":
        for quarter, ((start_month, _), (end_month, _)) in _QUARTERS.items():
            if start_month <= d.month <= end_month:
                return cls(d.year, quarter)
        raise AssertionError("unreachable: quarters cover all months")

    @classmethod
    def parse(cls, text: str, today: date) -> "TaxQuarter":
        """Parse '2026q2', '2026Q2', or 'q2' (current year)."""
        match = _QUARTER_RE.match(text.strip())
        if match is None:
            raise TtdError(f"Can't parse quarter {text!r} — use e.g. 2026q2 or q2")
        year = int(match.group(1)) if match.group(1) else today.year
        return cls(year, int(match.group(2)))


def quarters_of(year: int) -> list[TaxQuarter]:
    return [TaxQuarter(year, q) for q in sorted(_QUARTERS)]


def compute_set_aside(subtotal: Decimal, rate: Decimal) -> Decimal:
    """Cents-aligned share of an invoice subtotal to hold back for taxes."""
    return to_cents(subtotal * rate)


def format_rate(rate: Decimal) -> str:
    """``0.32`` → ``32%``; keeps fractional precision (``0.325`` → ``32.5%``)."""
    return f"{float(rate) * 100:g}%"
