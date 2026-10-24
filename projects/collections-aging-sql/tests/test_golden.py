"""Golden tests: a fresh run over the committed data must reproduce sample_output."""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest

from aging_sql.engine import OUTPUT_FILES, run_pipeline

from conftest import DATA_DIR, SAMPLE_OUTPUT_DIR


@pytest.mark.parametrize("filename", OUTPUT_FILES)
def test_output_file_matches_sample_output(tmp_path: Path, filename: str) -> None:
    out_dir = tmp_path / "out"
    run_pipeline(
        invoices_path=DATA_DIR / "invoices.csv",
        payments_path=DATA_DIR / "payments.csv",
        out_dir=out_dir,
    )

    assert filecmp.cmp(out_dir / filename, SAMPLE_OUTPUT_DIR / filename, shallow=False)
