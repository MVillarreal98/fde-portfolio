"""CLI exit-code contract and argument handling."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from aging_sql.cli import main

from conftest import DATA_DIR, write_csv

INVOICES_CSV = DATA_DIR / "invoices.csv"
PAYMENTS_CSV = DATA_DIR / "payments.csv"


def run_cli(tmp_path: Path, *extra: str) -> int:
    return main(
        [
            "--invoices",
            str(INVOICES_CSV),
            "--payments",
            str(PAYMENTS_CSV),
            "--out",
            str(tmp_path / "out"),
            *extra,
        ]
    )


def test_demo_data_completes_zero_exit(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        assert run_cli(tmp_path) == 0
    assert any("findings: 3" in message for message in caplog.messages)


def test_demo_data_skipped_when_available(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        assert run_cli(tmp_path, "--fail-on-findings") == 2
        assert "findings: 3" in caplog.messages


def test_unreadable_input_exits_1(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    payments = write_csv(
        tmp_path / "payments.csv", ["payment_id", "paid_date"], [["PAY-1", "2026-09-01"]]
    )
    assert (
        main(
            [
                "--invoices",
                str(DATA_DIR / "invoices.csv"),
                "--payments",
                str(payments),
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )
    assert any("could not stage" in message for message in caplog.messages)


def test_bad_as_of_date_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run_cli(tmp_path, "--as-of", "30-09-2026")
    # 4 = argument rejected before the pipeline ran. 2 is reserved for
    # findings under --fail-on-findings; a scheduler must never page AR
    # because an operator typo'd a date.
    assert excinfo.value.code == 4


def test_version_flag(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "collections-aging 1.0.0" in capsys.readouterr().out
