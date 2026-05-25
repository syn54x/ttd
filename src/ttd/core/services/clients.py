"""Client CRUD services."""

from __future__ import annotations

from uuid import UUID, uuid4

from ferro.exceptions import ModelDoesNotExist

from ttd.core.exceptions import NotFoundError, ValidationError
from ttd.core.models.client import Client
from ttd.core.models.project import Project
from ttd.core.schemas import CreateClient, UpdateClient


async def create_client(data: CreateClient) -> Client:
    client = Client(
        id=uuid4(),
        name=data.name.strip(),
        default_hourly_rate=data.default_hourly_rate,
        currency=data.currency.upper(),
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
