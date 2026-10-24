"""Conservation invariants, rejected-row export and report content."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from reconciliation import Config, ReconciliationIntegrityError, run_reconciliation
from reconciliation import pipeline as pipeline_mod
from reconciliation.report import cents_to_text, to_display

from conftest import RunCase, write_case


def test_conservation_holds_and_is_reported(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        ",B,OXXO,20.00,MXN,captured,2025-03-01 09:00\n"
        "T3,C,OXXO,oops,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\nS2,,7.00,MXN,2025-03-02,1\n",
    )
    ops = res.stats["ops"]
    assert (ops.rows_read, ops.rows_processed, ops.rows_rejected) == (3, 1, 2)
    assert (ops.amount_read_cents, ops.amount_processed_cents, ops.amount_rejected_cents) == (
        12000,
        10000,
        2000,
    )
    assert ops.unparseable_amounts == 1
    report = Path(res.report_path).read_text(encoding="utf-8")
    assert "Conservation checks passed" in report
    rejected_csv = pd.read_csv(res.rejected_path, dtype=str, keep_default_na=False)
    assert rejected_csv["reason"].tolist() == [
        "missing transaction_id",
        "unparseable amount",
        "missing transaction_ref",
    ]
    assert rejected_csv["parsed_amount"].tolist() == ["20.00", "", "7.00"]


def test_row_loss_during_cleaning_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_clean_ops = pipeline_mod.clean_ops

    def lossy(raw: pd.DataFrame):
        clean, rejected = real_clean_ops(raw)
        return clean.iloc[1:], rejected  # a row disappears without being rejected

    monkeypatch.setattr(pipeline_mod, "clean_ops", lossy)
    ops, billing = write_case(
        tmp_path,
        "T1,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n"
        "T2,A,OXXO,2.00,MXN,captured,2025-03-01 09:00\n",
        "",
    )
    with pytest.raises(ReconciliationIntegrityError, match=r"\[ops\] rows read 2"):
        run_reconciliation(Config(ops_path=ops, billing_path=billing, output_dir=tmp_path / "out"))


def test_amount_drift_during_cleaning_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_clean_billing = pipeline_mod.clean_billing

    def drifting(raw: pd.DataFrame):
        clean, rejected = real_clean_billing(raw)
        clean["amount_cents"] = clean["amount_cents"] + 1
        return clean, rejected

    monkeypatch.setattr(pipeline_mod, "clean_billing", drifting)
    ops, billing = write_case(tmp_path, "", "S1,T1,1.00,MXN,2025-03-02,1\n")
    with pytest.raises(ReconciliationIntegrityError, match=r"\[billing\] amount read"):
        run_reconciliation(Config(ops_path=ops, billing_path=billing, output_dir=tmp_path / "out"))


@pytest.mark.parametrize("engine", ["pandas", "sql"])
def test_join_that_multiplies_rows_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    real_engine = pipeline_mod.get_engine(engine)

    def inflating(ops, billing, cfg):
        matched, findings = real_engine(ops, billing, cfg)
        return pd.concat([matched, matched.head(1)], ignore_index=True), findings

    monkeypatch.setattr(pipeline_mod, "get_engine", lambda name: inflating)
    ops, billing = write_case(
        tmp_path, "T1,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n", "S1,T1,1.00,MXN,2025-03-02,1\n"
    )
    with pytest.raises(ReconciliationIntegrityError, match="does not conserve inputs"):
        run_reconciliation(
            Config(ops_path=ops, billing_path=billing, output_dir=tmp_path / "out", engine=engine)
        )


def test_report_without_findings(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n", "S1,T1,1.00,MXN,2025-03-02,1\n"
    )
    report = Path(res.report_path).read_text(encoding="utf-8")
    assert "No anomalies detected" in report
    assert "## Rejected rows" not in report
    assert pd.read_csv(res.rejected_path).empty


def test_report_caps_rejected_rows(run_case: RunCase) -> None:
    ops = ",A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n" * 60
    res = run_case(ops, "")
    report = Path(res.report_path).read_text(encoding="utf-8")
    assert "## Rejected rows (60)" in report
    assert "_First 50 of 60 shown._" in report
    assert len(pd.read_csv(res.rejected_path)) == 60


def test_report_lists_mixed_currencies(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,CARD,1.00,USD,captured,2025-03-01 09:00\n", "S1,T1,1.00,MXN,2025-03-02,1\n"
    )
    assert "**Currencies in input:** MXN, USD" in Path(res.report_path).read_text("utf-8")


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "0.00"),
        (5, "0.05"),
        (-5, "-0.05"),
        (125000, "1250.00"),
        (-30000, "-300.00"),
        (None, ""),
        (pd.NA, ""),
    ],
)
def test_cents_to_text(cents: object, text: str) -> None:
    assert cents_to_text(cents) == text


def test_to_display_renames_money_and_formats_time() -> None:
    df = pd.DataFrame(
        {
            "ops_amount_cents": [125050],
            "first_recorded_at": pd.to_datetime(["2025-03-01 17:45"]),
            "merchant": ["A"],
        }
    )
    out = to_display(df)
    assert out.to_dict("records") == [
        {"ops_amount": "1250.50", "first_recorded_at": "2025-03-01 17:45", "merchant": "A"}
    ]
