"""Client CRUD services."""

from __future__ import annotations

from uuid import UUID, uuid4

from ferro.exceptions import ModelDoesNotExist

from ttd.core.exceptions import NotFoundError, ValidationError
from ttd.core.models.client import Client
from ttd.core.models.project import Project
from ttd.core.schemas import CreateClient, UpdateClient


def _validate_rounding_minutes(value: int | None) -> None:
    if value is not None and value <= 0:
        raise ValidationError("rounding_increment_minutes must be a positive integer")


async def create_client(data: CreateClient) -> Client:
    _validate_rounding_minutes(data.rounding_increment_minutes)
    client = Client(
        id=uuid4(),
        name=data.name.strip(),
        default_hourly_rate=data.default_hourly_rate,
        currency=data.currency.upper(),
        rounding_increment_minutes=data.rounding_increment_minutes,
    )
    await client.save()
    return client


async def get_client(client_id: UUID) -> Client:
    client = await Client.get_or_none(client_id)
    if client is None:
        raise NotFoundError(f"Client {client_id} not found")
    return client


async def list_clients() -> list[Client]:
    return await Client.all()


async def update_client(client_id: UUID, data: UpdateClient) -> Client:
    client = await get_client(client_id)
    if data.name is not None:
        client.name = data.name.strip()
    if data.default_hourly_rate is not None:
        client.default_hourly_rate = data.default_hourly_rate
    if data.currency is not None:
        client.currency = data.currency.upper()
    if data.clear_rounding_increment:
        client.rounding_increment_minutes = None
    elif data.rounding_increment_minutes is not None:
        _validate_rounding_minutes(data.rounding_increment_minutes)
        client.rounding_increment_minutes = data.rounding_increment_minutes
    await client.save()
    return client


async def delete_client(client_id: UUID) -> None:
    client = await get_client(client_id)
    projects = await Project.where(lambda p: p.client_id == client.id).all()
    if projects:
        raise ValidationError("Cannot delete client with existing projects")
    try:
        await client.delete()
    except ModelDoesNotExist:
        raise NotFoundError(f"Client {client_id} not found") from None
