"""Settings model. Loaded by ttd.config.loader; frozen after load."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _to_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, Decimal):
        return value
    # Route floats through str so TOML `150.0` doesn't pick up binary noise
    return Decimal(str(value))


class UserConfig(_Section):
    name: str = ""
    email: str = ""
    address: str = ""


class BusinessConfig(_Section):
    currency: str = "USD"
    default_hourly_rate: Decimal | None = None

    _rate = field_validator("default_hourly_rate", mode="before")(_to_decimal)


class InvoiceConfig(_Section):
    number_format: str = "{year}-{seq:03d}"
    payment_terms_days: int = 30
    tax_rate: Decimal = Decimal("0")
    # validate_default so the default goes through expanduser too — pydantic
    # skips validators on defaults otherwise, which left a literal "~" path
    output_dir: Path = Field(default=Path("~/Documents/invoices"), validate_default=True)

    _tax = field_validator("tax_rate", mode="before")(_to_decimal)

    @field_validator("output_dir", mode="after")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()


class BillingConfig(_Section):
    rounding: Literal["nearest", "up", "none"] = "nearest"
    increment_minutes: int = 15


class DisplayConfig(_Section):
    time_format: Literal["12h", "24h"] = "12h"
    week_start: Literal["monday", "sunday"] = "monday"
    theme: str = "ttd-dark"


class ParsingConfig(_Section):
    workday_start: int = 7
    workday_end: int = 19


class DefaultsConfig(_Section):
    client: str | None = None
    project: str | None = None
    billable: bool = True


class StorageConfig(_Section):
    db_path: Path | None = None

    @field_validator("db_path", mode="after")
    @classmethod
    def _expand(cls, v: Path | None) -> Path | None:
        return v.expanduser() if v else None


class Settings(_Section):
    user: UserConfig = UserConfig()
    business: BusinessConfig = BusinessConfig()
    invoice: InvoiceConfig = InvoiceConfig()
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
