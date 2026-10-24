"""Shared helpers for the collections-aging tests."""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from aging_sql.engine import AS_OF_DEFAULT, run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_OUTPUT_DIR = PROJECT_ROOT / "sample_output"

INVOICE_HEADER = [
    "invoice_id",
    "customer_id",
    "customer_name",
    "issued_date",
    "due_date",
    "amount_cents",
]
PAYMENT_HEADER = [
    "payment_id",
    "invoice_id",
    "paid_date",
    "amount_cents",
    "method",
]


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


@pytest.fixture()
def invoices_csv(tmp_path: Path) -> Callable[..., Path]:
    def _write(rows: list[list[Any]]) -> Path:
        return write_csv(tmp_path / "invoices.csv", INVOICE_HEADER, rows)

    return _write


@pytest.fixture()
def payments_csv(tmp_path: Path) -> Callable[..., Path]:
    def _write(rows: list[list[Any]]) -> Path:
        return write_csv(tmp_path / "payments.csv", PAYMENT_HEADER, rows)

    return _write


@pytest.fixture()
def run_aging(
    tmp_path: Path,
    invoices_csv: Callable[..., Path],
    payments_csv: Callable[..., Path],
) -> Callable[..., Path]:
    """Runs the pipeline on fixture rows (raw row lists) and returns the out dir."""

    logging.disable(logging.CRITICAL)
    try:

        def _run(
            invoice_rows: list[list[Any]],
            payment_rows: list[list[Any]],
            as_of: str = AS_OF_DEFAULT,
        ) -> Path:
            out_dir = tmp_path / "out"
            run_pipeline(
                invoices_path=invoices_csv(invoice_rows),
                payments_path=payments_csv(payment_rows),
                out_dir=out_dir,
                as_of=as_of,
            )
            return out_dir

        return _run
    finally:
        logging.disable(logging.NOTSET)


def read_rows(out_dir: Path, filename: str) -> list[dict[str, str]]:
    """Reads one output CSV back as string records for assertions."""
    with open(out_dir / filename, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def invoice(
    invoice_id: str,
    due: str,
    cents: int,
    customer: str = "C1",
    issued: str = "2026-08-01",
    name: str = "Demo Inc",
) -> list[Any]:
    return [invoice_id, customer, name, issued, due, cents]


def payment(
    payment_id: str,
    invoice_id: str,
    paid: str,
    cents: int,
    method: str = "OXXO",
) -> list[Any]:
    return [payment_id, invoice_id, paid, cents, method]


def find_row(
    rows: list[dict[str, str]],
    column: str,
    reference: str,
) -> dict[str, str]:
    matches = [row for row in rows if row[column] == reference]
    assert len(matches) == 1, f"expected exactly 1 row with {column}={reference}, got {matches}"
    return matches[0]


def finding_codes(out: Path) -> list[str]:
    return [row["code"] for row in read_rows(out, "findings.csv")]
