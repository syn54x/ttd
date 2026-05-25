"""Domain exceptions for ttd.core."""

from __future__ import annotations


class TTDError(Exception):
    """Base for core domain errors."""


class NotFoundError(TTDError):
    """Raised when a requested entity does not exist."""


class ValidationError(TTDError):
    """Raised when input violates domain rules."""
