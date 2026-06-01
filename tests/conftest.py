import pytest

from ttd.core.config import Settings, clear_settings_cache
from ttd.core.db import close_db, init_db
from ttd.core.models.client import Client
from ttd.core.models.enums import BillingMode
from ttd.core.models.project import Project
from ttd.core.schemas import CreateClient, CreateProject
from ttd.core.services import clients as client_service
from ttd.core.services import projects as project_service


@pytest.fixture(autouse=True)
def isolate_app_config(monkeypatch, tmp_path) -> None:
    """Keep layered TOML/env config from the developer machine out of tests."""
    xdg = tmp_path / "xdg-config"
    xdg.mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    for var in ("TTD_DATA_DIR", "TTD_DB_FILENAME", "TTD_CLOCK_FORMAT"):
        monkeypatch.delenv(var, raising=False)
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
async def reset_db_state() -> None:
    await close_db()
    yield
    await close_db()


@pytest.fixture
def settings(tmp_path) -> Settings:
    data_dir = tmp_path / "ttd-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(data_dir=data_dir, db_filename="test.db")


@pytest.fixture
async def db(settings, reset_db_state) -> Settings:
    await init_db(settings)
    return settings


@pytest.fixture
async def sample_client(db) -> Client:

    return await client_service.create_client(
        CreateClient(name="Acme", default_hourly_rate="150", currency="USD")
    )


@pytest.fixture
async def hourly_project(db, sample_client) -> Project:

    return await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Website",
            billing_mode=BillingMode.HOURLY,
        )
    )


@pytest.fixture
async def fixed_price_project(db, sample_client) -> Project:

    return await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="App rebuild",
            billing_mode=BillingMode.FIXED_PRICE,
            contract_total="10000",
            currency="USD",
        )
    )
