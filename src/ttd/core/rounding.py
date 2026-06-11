"""Billing rounding policies.

Rounding applies to the rolled-up seconds of one project-day, never to
individual entries — that matches how the hours appear on an invoice line.
"""

from ttd.config.schema import BillingConfig


def round_seconds(seconds: int, config: BillingConfig) -> int:
    if seconds <= 0:
        return 0
    if config.rounding == "none" or config.increment_minutes <= 0:
        return seconds
    increment = config.increment_minutes * 60
    if config.rounding == "up":
        return ((seconds + increment - 1) // increment) * increment
    # nearest, half rounds up
    return ((seconds + increment // 2) // increment) * increment
