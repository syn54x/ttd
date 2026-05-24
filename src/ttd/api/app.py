from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from litestar import Litestar, get

from ttd.core.db import close_db, init_db
from ttd.core.services import health


@get("/health")
async def health_route() -> dict[str, str]:
    result = await health.ping()
    return {"status": result["status"], "db_path": result["db_path"]}


@asynccontextmanager
async def lifespan(_app: Litestar) -> AsyncIterator[None]:
    await init_db()
    try:
        yield
    finally:
        await close_db()


def create_app() -> Litestar:
    return Litestar(route_handlers=[health_route], lifespan=[lifespan])


def run() -> None:
    import uvicorn

    uvicorn.run(
        "ttd.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
