"""Decimal money helpers. Floats never touch money."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ttd.core.errors import TtdError

CENT = Decimal("0.01")

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "$", "AUD": "$"}


def parse_money(raw: str | float | Decimal) -> Decimal:
    """Parse user input like '150', '150.50', '$150' into a Decimal."""
    if isinstance(raw, Decimal):
        return raw
    text = str(raw).strip().lstrip("$€£").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise TtdError(f"Not a valid amount: {raw!r}") from exc


def to_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def format_money(amount: Decimal, currency: str = "USD") -> str:
    symbol = CURRENCY_SYMBOLS.get(currency.upper())
    quantized = to_cents(amount)
    return f"{symbol}{quantized:,.2f}" if symbol else f"{quantized:,.2f} {currency.upper()}"


def hours(seconds: int) -> Decimal:
    """Seconds → decimal hours (2dp display precision happens at render)."""
    return Decimal(seconds) / Decimal(3600)


def format_hours(seconds: int) -> str:
    """Seconds → 'H:MM' clock-style display."""
    h, rem = divmod(seconds, 3600)
    return f"{h}:{rem // 60:02d}"
