"""Tests for natural-language time parsing."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from ttd.core.exceptions import ValidationError
from ttd.core.time import (
    parse_interval_parts,
    parse_interval_phrase,
    parse_work_date,
)


@pytest.fixture
def anchored_now() -> datetime:
    return datetime(2026, 5, 26, 14, 0)


def test_parse_work_date_iso() -> None:
    assert parse_work_date("2026-05-21") == date(2026, 5, 21)


def test_parse_work_date_today(anchored_now: datetime) -> None:
    assert parse_work_date("today", now=anchored_now) == date(2026, 5, 26)


def test_parse_interval_phrase(anchored_now: datetime) -> None:
    interval = parse_interval_phrase("today 8am to 5pm", now=anchored_now)
    assert interval.work_date == date(2026, 5, 26)
    assert interval.started_at == datetime(2026, 5, 26, 8, 0, tzinfo=UTC)
    assert interval.ended_at == datetime(2026, 5, 26, 17, 0, tzinfo=UTC)


def test_parse_interval_parts_iso_date(anchored_now: datetime) -> None:
    interval = parse_interval_parts(
        work_date="2026-05-21",
        time_from="9am",
        time_to="11:30am",
        now=anchored_now,
    )
    assert interval.work_date == date(2026, 5, 21)
    assert interval.started_at == datetime(2026, 5, 21, 9, 0, tzinfo=UTC)
    assert interval.ended_at == datetime(2026, 5, 21, 11, 30, tzinfo=UTC)


def test_parse_interval_phrase_rejects_invalid(anchored_now: datetime) -> None:
    with pytest.raises(ValidationError):
        parse_interval_phrase("not a real interval", now=anchored_now)
