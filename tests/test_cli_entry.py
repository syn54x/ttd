import pytest

from ttd.cli.main import app


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Terminal-native" in captured.out
