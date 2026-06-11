"""Domain errors. CLI and TUI translate these into user-facing messages."""


class TtdError(Exception):
    """Base for all domain errors."""


class NotFoundError(TtdError):
    """A referenced client/project/entry/invoice does not exist."""


class ConflictError(TtdError):
    """Uniqueness or state conflict (duplicate slug, timer already running, ...)."""


class InvoicedEntryError(TtdError):
    """Attempted to modify an entry that is locked to an invoice."""


class ConfigError(TtdError):
    """Invalid or unwritable configuration."""


class ParseError(TtdError):
    """A natural-language time spec could not be parsed."""


class AmbiguousTimeError(ParseError):
    """A time spec resolved to multiple plausible intervals."""

    def __init__(self, message: str, candidates: list[tuple[str, str]] | None = None) -> None:
        super().__init__(message)
        # (label, canonical-spec) pairs the UI can offer as choices
        self.candidates = candidates or []
