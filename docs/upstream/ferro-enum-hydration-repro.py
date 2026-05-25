#!/usr/bin/env -S uv run
# Minimal reproduction for ferro-orm enum hydration (see syn54x/ferro-orm issues).
#
# From the TTD repo (uses installed ferro-orm + ttd models):
#   uv run python docs/upstream/ferro-enum-hydration-repro.py
#
# Standalone module is ferro_enum_hydration_repro_standalone.py (ferro-orm only).

from __future__ import annotations

import asyncio
import sys


async def repro_ttd() -> None:
    """Consumer repro for ferro <= 0.10.3; passes once #65 / PR #66 is installed."""
    from ferro import reset_engine

    from ttd.core.db import close_db, init_db
    from ttd.core.models.enums import BillingMode
    from ttd.core.models.project import Project
    from ttd.core.schemas import CreateClient, CreateProject
    from ttd.core.services import clients as client_service
    from ttd.core.services import projects as project_service

    await init_db()
    try:
        client = await client_service.create_client(
            CreateClient(name="Repro Client", default_hourly_rate="100", currency="USD")
        )
        await project_service.create_project(
            CreateProject(
                client_id=client.id,
                name="Repro Project",
                billing_mode=BillingMode.HOURLY,
            )
        )
        # Drop identity map / connection so the next read is a cold DB hydrate.
        await close_db()
        reset_engine()
        await init_db()

        loaded = (await Project.all())[-1]
        print(f"billing_mode type after cold load: {type(loaded.billing_mode).__name__}")
        print(f"billing_mode value: {loaded.billing_mode!r}")
        print(f"Project._enum_fields: {getattr(Project, '_enum_fields', {})}")
        # Plain str only — isinstance(..., str) is True for StrEnum members too.
        if type(loaded.billing_mode) is str:
            try:
                loaded.billing_mode.value  # noqa: B018
            except AttributeError as exc:
                print(f"AttributeError on .value (expected): {exc}")
            raise AssertionError(
                "cold load returned str; expected BillingMode after _fix_types"
            )
        if not isinstance(loaded.billing_mode, BillingMode):
            raise AssertionError(
                f"expected BillingMode, got {type(loaded.billing_mode).__name__}"
            )
        print("OK: enum hydrated")
    finally:
        await close_db()


def main() -> None:
    try:
        asyncio.run(repro_ttd())
    except AttributeError as exc:
        print(f"FAIL (AttributeError): {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
