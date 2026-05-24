from ttd.tui.app import TtdApp


def test_tui_app_imports() -> None:
    assert TtdApp.TITLE == "TTD"
