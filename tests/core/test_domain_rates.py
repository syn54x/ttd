from decimal import Decimal
from uuid import uuid4

import pytest

from ttd.core.domain.rates import effective_hourly_rate, implied_hourly_rate
from ttd.core.exceptions import ValidationError
from ttd.core.models.client import Client
from ttd.core.models.enums import BillingMode
from ttd.core.models.project import Project


def _client() -> Client:
    return Client(
        id=uuid4(),
        name="Acme",
        default_hourly_rate=Decimal("150"),
        currency="USD",
    )


def test_effective_rate_inherits_client() -> None:
    client = _client()
    project = Project(
        id=uuid4(),
        client_id=client.id,
        name="P",
        billing_mode=BillingMode.HOURLY,
        hourly_rate=None,
        currency=None,
    )
    assert effective_hourly_rate(client, project) == (Decimal("150"), "USD")


def test_effective_rate_project_override() -> None:
    client = _client()
    project = Project(
        id=uuid4(),
        client_id=client.id,
        name="P",
        billing_mode=BillingMode.HOURLY,
        hourly_rate=Decimal("175"),
        currency="CAD",
    )
    assert effective_hourly_rate(client, project) == (Decimal("175"), "CAD")


def test_implied_rate_with_hours() -> None:
    result = implied_hourly_rate(Decimal("10000"), "USD", Decimal("40"))
    assert result is not None
    assert result.amount == Decimal("250")
    assert result.currency == "USD"


def test_implied_rate_zero_hours_returns_none() -> None:
    assert implied_hourly_rate(Decimal("10000"), "USD", Decimal("0")) is None


def test_effective_rate_fixed_price_raises() -> None:
    client = _client()
    project = Project(
        id=uuid4(),
        client_id=client.id,
        name="P",
        billing_mode=BillingMode.FIXED_PRICE,
        contract_total=Decimal("10000"),
        currency="USD",
    )
    with pytest.raises(ValidationError, match="hourly"):
        effective_hourly_rate(client, project)
