"""Settings model. Loaded by ttd.config.loader; frozen after load."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)


def _to_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, Decimal):
        return value
    # Route floats through str so TOML `150.0` doesn't pick up binary noise
    return Decimal(str(value))


class UserConfig(_Section):
    name: str = ""
    """Your name, shown on invoices."""
    email: str = ""
    """Your email, shown on invoices."""
    address: str = ""
    """Your address, shown on invoices."""


class BusinessConfig(_Section):
    currency: str = "USD"
    """Currency code for rates and invoices."""
    default_hourly_rate: Decimal | None = None
    """Fallback hourly rate when client/project sets none."""

    _rate = field_validator("default_hourly_rate", mode="before")(_to_decimal)


class InvoiceConfig(_Section):
    number_format: str = "{year}-{seq:03d}"
    """Invoice number template; fields: {year}, {month}, {seq}."""
    payment_terms_days: int = 30
    """Days until an invoice is due."""
    tax_rate: Decimal = Decimal("0")
    """Tax added to invoices, as a fraction (0.08 = 8%)."""
    # validate_default so the default goes through expanduser too — pydantic
    # skips validators on defaults otherwise, which left a literal "~" path
    output_dir: Path = Field(default=Path("~/Documents/invoices"), validate_default=True)
    """Directory where rendered invoices are written."""

    _tax = field_validator("tax_rate", mode="before")(_to_decimal)

    @field_validator("output_dir", mode="after")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()


class TaxConfig(_Section):
    # The user's own set-aside rule, not tax law. 0 disables the feature.
    set_aside_rate: Decimal = Decimal("0")
    """Fraction of each paid invoice's subtotal to set aside for taxes (0 disables)."""

    _rate = field_validator("set_aside_rate", mode="before")(_to_decimal)

    @field_validator("set_aside_rate", mode="after")
    @classmethod
    def _bounded(cls, v: Decimal) -> Decimal:
        if not (Decimal("0") <= v < Decimal("1")):
            raise ValueError("set_aside_rate is a fraction — use 0.32 for 32%")
        return v


class BillingConfig(_Section):
    rounding: Literal["nearest", "up", "none"] = "nearest"
    """How billable time rounds to the increment."""
    increment_minutes: int = 15
    """Billing increment in minutes."""


class DisplayConfig(_Section):
    time_format: Literal["12h", "24h"] = "12h"
    """Clock format for displayed times."""
    week_start: Literal["monday", "sunday"] = "monday"
    """First day of the week in reports."""
    theme: str = "ttd-dark"
    """TUI theme name."""


class ParsingConfig(_Section):
    workday_start: int = 7
    """Workday start hour (0-23); disambiguates am/pm in parsed times."""
    workday_end: int = 19
    """Workday end hour (0-23); disambiguates am/pm in parsed times."""


class DefaultsConfig(_Section):
    client: str | None = None
    """Client slug assumed when --client is omitted."""
    project: str | None = None
    """Project slug assumed when --project is omitted."""
    billable: bool = True
    """Whether new entries are billable by default."""


class StorageConfig(_Section):
    db_path: Path | None = None
    """SQLite database path (default: platform user-data dir)."""

    @field_validator("db_path", mode="after")
    @classmethod
    def _expand(cls, v: Path | None) -> Path | None:
        return v.expanduser() if v else None


class Settings(_Section):
    user: UserConfig = UserConfig()
    business: BusinessConfig = BusinessConfig()
    invoice: InvoiceConfig = InvoiceConfig()
    tax: TaxConfig = TaxConfig()
    billing: BillingConfig = BillingConfig()
    display: DisplayConfig = DisplayConfig()
    parsing: ParsingConfig = ParsingConfig()
    defaults: DefaultsConfig = DefaultsConfig()
    storage: StorageConfig = StorageConfig()

    @property
    def db_path(self) -> Path:
        if self.storage.db_path is not None:
            return self.storage.db_path
        return Path(platformdirs.user_data_dir("ttd")) / "ttd.db"

    @property
    def db_dsn(self) -> str:
        return f"sqlite:{self.db_path}?mode=rwc"
