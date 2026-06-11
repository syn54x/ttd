"""Invoice numbering from the configured format template.

The format may use {year}, {month}, {seq}; seq increments within whatever
prefix the rendered template produces (a new year naturally resets it).
Numbers are unique forever — voided invoices keep theirs.
"""

from datetime import date

from ttd.core.errors import ConfigError

MAX_SEQ = 100_000


def next_number(fmt: str, existing: set[str], issued: date) -> str:
    try:
        for seq in range(1, MAX_SEQ):
            candidate = fmt.format(year=issued.year, month=issued.month, seq=seq)
            if candidate not in existing:
                return candidate
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError(
            f"Bad invoice.number_format {fmt!r} ({exc}) — use fields year, month, seq"
        ) from exc
    raise ConfigError(f"Ran out of invoice numbers for format {fmt!r}")
