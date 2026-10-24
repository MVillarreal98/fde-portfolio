"""Deterministic CSV and Markdown output for query results."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import date
from pathlib import Path

Row = Sequence[object]


def cents_to_decimal_str(cents: int | None) -> str:
    """Formats integer cents as an exact decimal string, never a float."""
    if cents is None:
        return ""
    value = abs(cents)
    sign = "-" if cents < 0 else ""
    return f"{sign}{value // 100}.{value % 100:02d}"


def format_cents(cents: int | None) -> str:
    """Formats integer cents for reports, with thousands separators."""
    if cents is None:
        return "0"
    return f"{cents:,}"


def _cell(column: str, value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int) and column.endswith("_cents"):
        return cents_to_decimal_str(value)
    return str(value)


def write_rows_csv(columns: Sequence[str], rows: Sequence[Row], path: Path) -> int:
    """Writes one CSV file; the header is written even when the report is empty."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(columns))
        for row in rows:
            writer.writerow(
                [_cell(column, value) for column, value in zip(columns, row, strict=False)]
            )
    return len(rows)
