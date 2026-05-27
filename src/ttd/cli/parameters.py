"""Shared cyclopts parameter aliases."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter

InteractiveOpt = Annotated[
    bool,
    Parameter(
        name=["-i", "--interactive"],
        help="Prompt for missing fields (default when the command has no args).",
    ),
]
