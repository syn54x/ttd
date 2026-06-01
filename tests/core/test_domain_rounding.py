from decimal import Decimal
from uuid import uuid4

from ttd.core.domain.rounding import effective_rounding_increment, round_hours_up
from ttd.core.models.client import Client
from ttd.core.models.project import Project


def _client(*, rounding: int | None = None) -> Client:
    return Client(
        id=uuid4(),
        name="Acme",
        default_hourly_rate=Decimal("150"),
        currency="USD",
        rounding_increment_minutes=rounding,
    )


def _project(client: Client, *, rounding: int | None = None) -> Project:
    from ttd.core.models.enums import BillingMode

    return Project(
        id=uuid4(),
        client_id=client.id,
        name="Website",
        billing_mode=BillingMode.HOURLY,
        rounding_increment_minutes=rounding,
    )


def test_round_hours_up_no_increment() -> None:
    assert round_hours_up(Decimal("2.37"), None) == Decimal("2.37")


def test_round_hours_up_fifteen_minutes() -> None:
    assert round_hours_up(Decimal("2.10"), 15) == Decimal("2.25")


def test_round_hours_up_exact_boundary() -> None:
    assert round_hours_up(Decimal("2.25"), 15) == Decimal("2.25")


def test_effective_rounding_inherits_client() -> None:
    client = _client(rounding=15)
    project = _project(client, rounding=None)
    assert effective_rounding_increment(client, project) == 15


def test_effective_rounding_project_override() -> None:
    client = _client(rounding=15)
    project = _project(client, rounding=6)
    assert effective_rounding_increment(client, project) == 6


def test_effective_rounding_ignores_field_proxy() -> None:
    client = _client()
    project = _project(client, rounding=15)
    object.__setattr__(client, "rounding_increment_minutes", object())
    assert effective_rounding_increment(client, project) == 15

    client = _client()
    project = _project(client)
    object.__setattr__(client, "rounding_increment_minutes", object())
    object.__setattr__(project, "rounding_increment_minutes", object())
    assert effective_rounding_increment(client, project) is None
