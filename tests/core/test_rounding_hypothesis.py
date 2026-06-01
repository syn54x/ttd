"""Hypothesis property tests for export rounding."""

from decimal import Decimal
from uuid import uuid4

from hypothesis import given
from hypothesis import strategies as st

from ttd.core.domain.rounding import effective_rounding_increment, round_hours_up
from ttd.core.models.client import Client
from ttd.core.models.enums import BillingMode
from ttd.core.models.project import Project


@given(
    hours=st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("1000"),
        allow_nan=False,
        allow_infinity=False,
        places=4,
    ),
    increment=st.one_of(st.none(), st.integers(min_value=1, max_value=240)),
)
def test_round_hours_up_is_monotonic(hours: Decimal, increment: int | None) -> None:
    rounded = round_hours_up(hours, increment)
    assert rounded >= hours


@given(
    hours=st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("1000"),
        allow_nan=False,
        allow_infinity=False,
        places=4,
    ),
    increment=st.integers(min_value=1, max_value=240),
)
def test_round_hours_up_respects_increment(hours: Decimal, increment: int) -> None:
    rounded = round_hours_up(hours, increment)
    increment_hours = Decimal(increment) / Decimal(60)
    units = (rounded / increment_hours).to_integral_value()
    assert rounded == units * increment_hours


def _client(*, rounding: int | None = None) -> Client:
    return Client(
        id=uuid4(),
        name="Acme",
        default_hourly_rate=Decimal("100"),
        currency="USD",
        rounding_increment_minutes=rounding,
    )


def _project(client: Client, *, rounding: int | None = None) -> Project:
    assert client.id is not None
    return Project(
        id=uuid4(),
        client_id=client.id,
        name="Work",
        billing_mode=BillingMode.HOURLY,
        rounding_increment_minutes=rounding,
    )


@given(
    client_inc=st.one_of(st.none(), st.integers(min_value=1, max_value=120)),
    project_inc=st.one_of(st.none(), st.integers(min_value=1, max_value=120)),
)
def test_effective_rounding_inheritance(
    client_inc: int | None,
    project_inc: int | None,
) -> None:
    client = _client(rounding=client_inc)
    project = _project(client, rounding=project_inc)
    expected = project_inc if project_inc is not None else client_inc
    assert effective_rounding_increment(client, project) == expected
