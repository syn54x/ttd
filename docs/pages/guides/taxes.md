# Taxes

Freelance income arrives untaxed; the IRS still wants its share quarterly.
ttd tracks the slice of each paid invoice you've earmarked for taxes and how
much you've actually remitted, so the answer to "am I covered this quarter?"
is one command.

## The set-aside idea

Pick a fraction of every paid invoice to set aside:

```console
$ ttd config set tax.set_aside_rate 0.30    # 30%
```

It's **your** rule of thumb — ttd applies whatever you choose to each paid
invoice's subtotal. `0` (the default) turns the feature off.

## When set-aside is calculated

At the moment an invoice is [marked paid](invoicing.md#the-invoice-lifecycle).
The amount and the rate used are frozen onto that invoice, so changing
`set_aside_rate` later never rewrites history — your records keep matching
what actually moved to your savings account. Re-marking with a corrected
`--paid-date` re-files the set-aside into the right quarter.

## Estimated-tax quarters

ttd uses the IRS estimated-tax calendar (note the uneven windows):

| Quarter | Window | Payment due |
| --- | --- | --- |
| Q1 | Jan 1 – Mar 31 | Apr 15 |
| Q2 | Apr 1 – May 31 | Jun 15 |
| Q3 | Jun 1 – Aug 31 | Sep 15 |
| Q4 | Sep 1 – Dec 31 | Jan 15 (next year) |

## Checking where you stand

```console
$ ttd tax status            # current year
$ ttd tax status --year 2025
```

One row per quarter: invoiced income, set-aside (from paid invoices),
remitted (payments you've recorded), and the balance still owed to your
future self. Negative-or-zero balance: covered.

## Recording a payment

When you pay the IRS, tell ttd:

```console
$ ttd tax pay q2 4500                        # current year's Q2
$ ttd tax pay 2026q2 4500 --date 2026-06-10 --note "EFTPS confirmation 12345"
```

Quarters are written `2026q2` or just `q2` for the current year.

## Reviewing and correcting

```console
$ ttd tax payments              # this year's recorded payments
$ ttd tax payments --year 2025
$ ttd tax rm a3f2               # delete a mistaken payment (id prefix ok)
```

## Taxes in the TUI

Screen `6` is the same dashboard, with `p` to record a payment and `[` / `]`
to change year:

![Tax dashboard](../assets/screenshots/taxes.svg)

!!! note
    ttd tracks money **you decided** to set aside — it doesn't compute your
    tax liability and nothing here is tax advice.
