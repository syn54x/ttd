"""Test runner for the Cyclopts app — stands in for typer.testing.CliRunner.

Captures combined stdout+stderr (the _output.py consoles resolve their file
at write time, so redirecting works) and catches the SystemExit that
cyclopts raises even on success.
"""

import contextlib
import io
from dataclasses import dataclass


@dataclass
class Result:
    exit_code: int
    output: str


class CliRunner:
    def invoke(self, app, args: list[str]) -> Result:
        buf = io.StringIO()
        exit_code = 0
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                app(args)
            except SystemExit as e:
                if isinstance(e.code, int):
                    exit_code = e.code
                elif e.code is not None:
                    exit_code = 1
        return Result(exit_code=exit_code, output=buf.getvalue())
