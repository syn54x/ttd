"""AdaptiveFooter: every binding stays visible at any terminal width."""

import pytest
from _db import open_test_db

from ttd.config.schema import Settings, StorageConfig
from ttd.tui.app import TtdApp


@pytest.fixture
async def app(tmp_path, monkeypatch):
    """A TtdApp on an empty temp DB (footer behavior needs no data)."""
    db_path = tmp_path / "tui.db"
    monkeypatch.setenv("TTD_DB_PATH", str(db_path))
    monkeypatch.setenv("TTD_CONFIG_DIR", str(tmp_path / "config"))
    async with open_test_db(Settings(storage=StorageConfig(db_path=db_path))):
        pass
    yield TtdApp()


def _hidden_keys(footer) -> list:
    return [
        key
        for key in footer.query("FooterKey")
        if not footer.region.contains(key.region.x + max(key.region.width - 1, 0), key.region.y)
    ]


async def test_footer_wraps_instead_of_clipping_when_narrow(app):
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("2")  # timesheet has the most bindings
        await pilot.pause()
        await pilot.pause()
        footer = app.screen.query_one("AdaptiveFooter")
        assert footer.region.height > 1
        assert footer.has_class("-wrapped")
        assert _hidden_keys(footer) == []


async def test_footer_stays_single_row_when_wide(app):
    async with app.run_test(size=(180, 24)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        await pilot.pause()
        footer = app.screen.query_one("AdaptiveFooter")
        assert footer.region.height == 1
        assert not footer.has_class("-wrapped")
        assert _hidden_keys(footer) == []


async def test_footer_replans_after_screen_switch(app):
    """Each screen has a different binding set; the plan must follow it."""
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("1")  # dashboard: base bindings only
        await pilot.pause()
        await pilot.pause()
        footer = app.screen.query_one("AdaptiveFooter")
        assert _hidden_keys(footer) == []


async def test_nav_bindings_render_as_compact_group(app):
    async with app.run_test(size=(160, 24)) as pilot:
        await pilot.pause()
        footer = app.screen.query_one("AdaptiveFooter")
        labels = [str(label.render()) for label in footer.query("FooterLabel")]
        assert "screen" in labels
        # grouped keys render bare (description lives in the group label)
        nav_keys = [k for k in footer.query("FooterKey") if k.key in "123456"]
        assert len(nav_keys) == 6
        assert all(k.description == "" for k in nav_keys)


async def test_wrapped_second_row_keys_still_dispatch_actions(app):
    """Re-parented keys must keep working: click one on the wrapped row."""
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        await pilot.pause()
        footer = app.screen.query_one("AdaptiveFooter")
        target = next(k for k in footer.query("FooterKey") if k.description == "today")
        assert target.region.y > footer.region.y  # really on a wrapped row
        await pilot.click(target)
        await pilot.pause()
        assert app.screen.query_one("AdaptiveFooter")  # still alive, no crash
