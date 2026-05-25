from decimal import Decimal

import pytest

from ttd.core.exceptions import NotFoundError, ValidationError
from ttd.core.schemas import CreateClient
from ttd.core.services import clients as client_service


async def test_create_and_get_client(db) -> None:
    created = await client_service.create_client(
        CreateClient(name="Acme", default_hourly_rate=Decimal("150"), currency="usd")
    )
    loaded = await client_service.get_client(created.id)
    assert loaded.name == "Acme"
    assert loaded.default_hourly_rate == Decimal("150")
    assert loaded.currency == "USD"


async def test_list_clients(db) -> None:
    await client_service.create_client(
        CreateClient(name="A", default_hourly_rate=Decimal("1"), currency="USD")
    )
    await client_service.create_client(
        CreateClient(name="B", default_hourly_rate=Decimal("2"), currency="USD")
    )
    names = {c.name for c in await client_service.list_clients()}
    assert names == {"A", "B"}


async def test_delete_client_without_projects(db) -> None:
    client = await client_service.create_client(
        CreateClient(name="Solo", default_hourly_rate=Decimal("1"), currency="USD")
    )
    await client_service.delete_client(client.id)
    with pytest.raises(NotFoundError):
        await client_service.get_client(client.id)


async def test_delete_client_with_projects_fails(db, hourly_project) -> None:
    with pytest.raises(ValidationError, match="projects"):
        await client_service.delete_client(hourly_project.client_id)


async def test_get_missing_client(db) -> None:
    from uuid import uuid4

    with pytest.raises(NotFoundError):
        await client_service.get_client(uuid4())
