"""Golden test: the bundled demo must reproduce the committed sample_output/ exactly.

Regenerate after an intentional change with:
    python run_reconciliation.py --out sample_output
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reconciliation import Config, run_reconciliation

from conftest import DATA, SAMPLE_OUTPUT


@pytest.mark.parametrize("engine", ["pandas", "sql"])
def test_demo_matches_sample_output(tmp_path: Path, engine: str) -> None:
    cfg = Config(
        ops_path=DATA / "ops_transactions.csv",
        billing_path=DATA / "billing_statements.csv",
        output_dir=tmp_path,
        engine=engine,
    )
    run_reconciliation(cfg)

    expected = sorted(p.name for p in SAMPLE_OUTPUT.iterdir())
    assert sorted(p.name for p in tmp_path.iterdir()) == expected
    for name in expected:
        want = (SAMPLE_OUTPUT / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        got = (tmp_path / name).read_text(encoding="utf-8")
        if name == "reconciliation_report.md":
            # sample_output was produced by the pandas engine; only that label may differ.
            got = got.replace(f"_Engine: {engine} ·", "_Engine: pandas ·", 1)
        assert got == want, name
