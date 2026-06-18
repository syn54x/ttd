# Configuration reference

Every setting ttd understands, with its type, default, and what it does. Each
section below corresponds to a TOML table: the key `billing.rounding` lives in
the config file as

```toml
[billing]
rounding = "up"
```

and can be changed from the command line with `ttd config set billing.rounding up`.
See the [Configuration guide](../guides/configuration.md) for where settings live
and how the layers interact.

## `[user]`

Identity shown on your invoices.

::: ttd.config.schema.UserConfig

## `[business]`

::: ttd.config.schema.BusinessConfig

## `[invoice]`

::: ttd.config.schema.InvoiceConfig

## `[tax]`

::: ttd.config.schema.TaxConfig

## `[billing]`

How logged time becomes billable time on invoices.

::: ttd.config.schema.BillingConfig

## `[display]`

::: ttd.config.schema.DisplayConfig

## `[parsing]`

::: ttd.config.schema.ParsingConfig

## `[defaults]`

Fallbacks used when a command omits `--client`, `--project`, or `--billable`.

::: ttd.config.schema.DefaultsConfig

## `[storage]`

::: ttd.config.schema.StorageConfig

## Complete example

A global config file (`~/.config/ttd/config.toml`) showing every setting at its
default value — you only ever need the keys you want to change:

```toml
[user]
name = ""                          # Your name, shown on invoices
email = ""                         # Your email, shown on invoices
address = ""                       # Your address, shown on invoices

[business]
currency = "USD"                   # Currency code for rates and invoices
# default_hourly_rate =            # Fallback rate when client/project sets none (unset)

[invoice]
number_format = "{year}-{seq:03d}" # Fields: {year}, {month}, {seq}
payment_terms_days = 30            # Days until an invoice is due
tax_rate = 0                       # Tax added to invoices, as a fraction (0.08 = 8%)
output_dir = "~/Documents/invoices"

[tax]
set_aside_rate = 0                 # Fraction of paid invoices to set aside (0 disables)

[billing]
rounding = "nearest"               # nearest | up | none
increment_minutes = 15             # Billing increment in minutes

[display]
time_format = "12h"                # 12h | 24h
week_start = "monday"              # monday | sunday
theme = "ttd-dark"                 # any Textual theme name

[parsing]
workday_start = 7                  # Hour (0-23); disambiguates am/pm in parsed times
workday_end = 19

[defaults]
# client =                         # Client slug assumed when --client is omitted (unset)
# project =                        # Project slug assumed when --project is omitted (unset)
billable = true                    # Whether new entries are billable by default

[storage]
# db_path =                        # SQLite path (default: platform user-data dir)
```
