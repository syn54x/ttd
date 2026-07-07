# Expenses

Bill back purchased items — subscriptions, software, travel — as **untaxed,
pass-through** line items on invoices. Expenses are separate from time: they
add to the invoice total after tax is calculated on billable hours only.

## Logging an expense

```console
$ ttd expense add "Claude Code" 100 -p api-rewrite
$ ttd expense add "Domain renewal" 15.99 -p api-rewrite --on 2026-06-15 \
    --note "annual" --receipt ~/Downloads/receipt.pdf
```

`-p` / `--project` is required. `--on` sets the incurred date (defaults to
today). Attach a receipt at creation with `--receipt PATH`.

In the TUI, press `l` anywhere and choose **$ expense**. The form asks for
project, description, amount, and date (blank = today). Receipt attach and
history recall are CLI-only for now.

## Listing expenses

```console
$ ttd expense list
$ ttd expense list -p api-rewrite --from 2026-06-01 --to 2026-06-30
$ ttd expense list --client acme-corp --unbilled
$ ttd expense list --json
```

Rows show date, project, description, amount, and flags: `·inv` when the
expense is on an invoice, `📎` when a receipt is attached. IDs are 8-character
prefixes.

The TUI **Log** screen (nav `2`) shows the same month's expenses in a second
table below time entries. See [The TUI](the-tui.md#log) and
[Managing entries](managing-entries.md#the-log-screen).

## Editing and deleting

```console
$ ttd expense edit a3f2 --amount 120 --description "Claude Code (annual)"
$ ttd expense rm a3f2
```

Once an expense is on an invoice, `edit` and `rm` refuse — void the invoice
first ([Invoicing](invoicing.md#the-invoice-lifecycle)), then change and
re-invoice.

## Receipts

Receipts are optional PDF or image files stored with the expense. Manage them
from the CLI:

```console
$ ttd expense receipt add a3f2 ~/Downloads/receipt.pdf
$ ttd expense receipt get a3f2 --out ./receipt.pdf
$ ttd expense receipt rm a3f2
```

Files larger than 5 MiB are rejected. When you render an invoice with
`--receipts` (or `invoice.attach_receipts` enabled in
[config](configuration.md#invoice-receipts)), receipt pages are merged into
the PDF after the invoice letterhead. Markdown cannot embed receipts — ttd
blocks `--md` when receipts would be included.

## On invoices

`invoice create` pulls **uninvoiced billable entries and expenses** in the
requested period. An invoice with only expenses (no time) is valid.

Expense amounts are **not taxed**. Invoice math:

```text
total = time_subtotal + tax + expenses_subtotal
```

Tax applies to the time subtotal only. Expenses appear as a separate
"Reimbursable expenses" section on PDF and Markdown renders.

When an invoice is created, linked expenses are locked (like time entries).
Voiding the invoice releases them for re-invoicing. Refresh recomputes expense
lines from locked data; the CLI shows expense subtotal diffs when they change.

The invoice's stored period is derived from the **actual line dates** (min–max
of time `work_date` and expense `incurred_date`), not necessarily the window
you requested — so a mid-month re-invoice shows the true span.

Full lifecycle, rendering, and period syntax: [Invoicing](invoicing.md).

## JSON backup

Expenses and receipts round-trip through JSON export only (envelope
`ttd_export: 2`). CSV, XLSX, and Numbers remain entry-only. See
[Import & export](import-export.md#json-envelope-v2) and
[Data & backups](data-and-backups.md#exports-as-archives).

## CLI reference

Every flag and subcommand: [`ttd expense`](../reference/cli/expense.md).

## Known limitations

- [`ttd invoice show`](../reference/cli/invoice.md) table output lists time
  lines only ([#17](https://github.com/syn54x/ttd/issues/17)); use
  `--format md`, TUI detail (`o`), or a rendered PDF for expense lines.
- [`ttd report`](reports.md) does not include expense totals
  ([#18](https://github.com/syn54x/ttd/issues/18)).
