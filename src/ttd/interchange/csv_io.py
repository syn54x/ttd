import csv
from pathlib import Path
from typing import Any

from ttd.interchange.base import Format, register
from ttd.interchange.model import COLUMNS, EntryRecord


def write_csv(records: list[EntryRecord], path: Path, meta: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_cells())


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip().lower(): v for k, v in row.items()} for row in csv.DictReader(f)]


register(Format("csv", ("csv",), write_csv, read_csv))
