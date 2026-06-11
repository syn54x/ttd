from datetime import datetime, time
from pathlib import Path
from typing import Any

from numbers_parser import Document

from ttd.core.errors import TtdError
from ttd.interchange.base import Format, register
from ttd.interchange.model import COLUMNS, EntryRecord


def write_numbers(records: list[EntryRecord], path: Path, meta: dict[str, Any]) -> None:
    doc = Document()
    table = doc.sheets[0].tables[0]
    for col, name in enumerate(COLUMNS):
        table.write(0, col, name)
    for row, record in enumerate(records, start=1):
        cells = record.to_cells()
        # Numbers cells: dates as datetime, numbers as numbers, the rest text
        values: list[Any] = [
            cells["uid"],
            cells["client"],
            cells["project"],
            datetime.combine(record.date, time.min),
            cells["start"],
            cells["end"],
            float(record.hours),
            record.seconds,
            cells["note"],
            cells["tags"],
            record.billable,
            cells["invoice_number"],
        ]
        for col, value in enumerate(values):
            table.write(row, col, value)
    # numbers-parser wants a fresh file: write to a temp name, then move into place
    tmp = path.parent / f".{path.stem}.tmp.numbers"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        tmp.unlink()
    doc.save(str(tmp))
    tmp.replace(path)


def read_numbers(path: Path) -> list[dict[str, Any]]:
    try:
        doc = Document(str(path))
    except Exception as exc:
        raise TtdError(f"{path} is not a readable Numbers document: {exc}") from exc
    table = doc.sheets[0].tables[0]
    rows = table.rows(values_only=True)
    if not rows:
        return []
    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    return [
        {key: value for key, value in zip(header, row, strict=False)}
        for row in rows[1:]
        if any(v is not None and str(v).strip() for v in row)
    ]


register(Format("numbers", ("numbers",), write_numbers, read_numbers))
