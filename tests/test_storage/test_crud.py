from decimal import Decimal

import pytest

from ttd.core.errors import ConflictError, NotFoundError
from ttd.services import clients as client_svc
from ttd.services import projects as project_svc


async def test_create_and_get_client(db):
    created = await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    fetched = await client_svc.get_client("acme-corp")
    assert fetched.id == created.id
    assert fetched.name == "Acme Corp"
    assert fetched.hourly_rate == Decimal("150")
    assert fetched.currency == "USD"


async def test_duplicate_client_slug_rejected(db):
    await client_svc.create_client("Acme")
    with pytest.raises(ConflictError):
        await client_svc.create_client("Acme")


async def test_get_missing_client(db):
    with pytest.raises(NotFoundError):
        await client_svc.get_client("nope")


async def test_archive_hides_from_list(db):
    await client_svc.create_client("Acme")
    await client_svc.create_client("Beta")
    await client_svc.archive_client("acme")
    slugs = [c.slug for c in await client_svc.list_clients()]
    assert slugs == ["beta"]
    slugs_all = [c.slug for c in await client_svc.list_clients(include_archived=True)]
    assert slugs_all == ["acme", "beta"]


async def test_update_client(db):
    await client_svc.create_client("Acme")
    updated = await client_svc.update_client("acme", hourly_rate=Decimal("175"), email="a@b.co")
    assert updated.hourly_rate == Decimal("175")
    assert updated.email == "a@b.co"


async def test_project_rate_inheritance(db):
    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    inherit = await project_svc.create_project("API", "acme")
    override = await project_svc.create_project("Design", "acme", hourly_rate=Decimal("200"))
    assert await project_svc.effective_rate(inherit) == Decimal("150")
    assert await project_svc.effective_rate(override) == Decimal("200")


async def test_project_slug_scoped_to_client(db):
    await client_svc.create_client("Acme")
    await client_svc.create_client("Beta")
    await project_svc.create_project("API", "acme")
    await project_svc.create_project("API", "beta")  # same slug, different client: fine
    with pytest.raises(ConflictError):
        await project_svc.create_project("API", "acme")
    # unscoped lookup is now ambiguous
    with pytest.raises(ConflictError):
        await project_svc.get_project("api")
    scoped = await project_svc.get_project("api", "beta")
    assert scoped.slug == "api"


async def test_delete_client_requires_force_with_projects(db):
    await client_svc.create_client("Acme")
    await project_svc.create_project("API", "acme")
    with pytest.raises(ConflictError):
        await client_svc.delete_client("acme")
    await client_svc.delete_client("acme", force=True)
    with pytest.raises(NotFoundError):
        await client_svc.get_client("acme")
