# Interchange format

The single tabular schema used by [`ttd export` and `ttd import`](../guides/import-export.md)
across all four file formats. Export and import are symmetric: ttd can always
re-import its own exports.

## Canonical columns

In order:

| Column | Type | Semantics |
| --- | --- | --- |
| `uid` | UUID string | ttd's entry id. Blank in foreign files; preferred match key on import. |
| `client` | string, **required** | Client slug (or name on import) |
| `project` | string, **required** | Project slug (or name on import) |
| `date` | `YYYY-MM-DD`, **required** | The work day the entry belongs to |
| `start` | `HH:MM:SS` or blank | Interval start; blank for duration-only entries |
| `end` | `HH:MM:SS` or blank | Interval end |
| `hours` | decimal | Convenience value (`seconds / 3600`); used on import only if `seconds` is missing |
| `seconds` | integer, **required** | The authoritative duration |
| `note` | string | Free text |
| `tags` | string | Comma-separated |
| `billable` | boolean | `true`/`false` (imports also accept `yes`/`no`/`1`/`0`/`x`) |
| `invoice_number` | string | Informational only — imports never (re)attach entries to invoices |

## File formats

| Format | Extension | Notes |
| --- | --- | --- |
| CSV | `.csv` | Header row, UTF-8 |
| JSON | `.json` | Array of objects + a top-level `_metadata` block (export timestamp, settings summary) |
| Excel | `.xlsx` | One sheet, header row, native date/time cells |
| Apple Numbers | `.numbers` | One table; readable and writable |

The format is inferred from the file extension, or forced with
`-f csv|json|xlsx|numbers`.

## Matching semantics

On import, each row is matched against existing entries:

1. by `uid`, when present
2. otherwise by content — same client, project, date, start, end, duration,
   and note

What happens to matches is set by `--on-conflict`: `skip` (default — makes
re-imports idempotent), `update` (the file wins), or `duplicate` (keep
both; the incoming row gets a new uid). **Invoiced entries are never
modified or re-linked**, regardless of mode.

## Examples

CSV:

```csv
uid,client,project,date,start,end,hours,seconds,note,tags,billable,invoice_number
,acme-corp,api-rewrite,2026-06-03,09:00:00,11:30:00,2.5,9000,auth endpoints,backend,true,
,acme-corp,api-rewrite,2026-06-04,,,2.0,7200,code review,,true,
```

JSON record:

```json
{
  "uid": "a3f2c9d0-5e1b-4f7a-9c2d-8b6e4a1f0c3e",
  "client": "acme-corp",
  "project": "api-rewrite",
  "date": "2026-06-03",
  "start": "09:00:00",
  "end": "11:30:00",
  "hours": 2.5,
  "seconds": 9000,
  "note": "auth endpoints",
  "tags": "backend",
  "billable": true,
  "invoice_number": null
}
```
