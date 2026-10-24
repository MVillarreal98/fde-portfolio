"""Duplicate-id rejection, exit-code contract and staging ordering."""

from __future__ import annotations

import pytest

from aging_sql.cli import main
from aging_sql.engine import AgingDataError, run_pipeline

from conftest import INVOICE_HEADER, PAYMENT_HEADER, invoice, payment, read_rows, write_csv


def test_duplicate_invoice_id_keeps_first_occurrence(run_aging) -> None:
    # A re-issued invoice with the same id is a duplicate: only the first
    # occurrence counts. The naive behaviour would report 160000 invoiced
    # and, with similar amounts, an overpayment finding; the deduped run
    # sees one invoice of 100000, no findings, no aging money.
    invoices = [
        invoice("D1", "2026-09-01", 100000, issued="2026-08-01"),
        invoice("D1", "2026-09-15", 60000, issued="2026-08-20"),
    ]
    payments = [payment("PD1", "D1", "2026-08-10", 100000)]

    out = run_aging(invoices, payments)

    rejected = read_rows(out, "rejected_rows.csv")
    dupes = [(row["source"], row["reason"]) for row in rejected]
    assert dupes == [("invoice", "duplicate_invoice_id")]
    assert [row["line_no"] for row in rejected] == ["2"]
    assert read_rows(out, "findings.csv") == []
    # History shows the invoice, not the duplicate: money is 100.000.
    with open(out / "collections_report.md", encoding="utf-8") as handle:
        report = handle.read()
    assert "invoiced | 100,000" in report


def test_duplicate_payment_id_keeps_first_occurrence(run_aging) -> None:
    # A re-loaded payment row must not silently pay the second half of the
    # invoice (the double-entry bug). The second occurrence is rejected.
    invoices = [invoice("E1", "2026-09-10", 120000, issued="2026-08-01")]
    payments = [
        payment("PE1", "E1", "2026-08-15", 60000),
        payment("PE1", "E1", "2026-08-20", 60000),
    ]

    out = run_aging(invoices, payments)

    rejected = read_rows(out, "rejected_rows.csv")
    assert [(row["source"], row["reason"], row["line_no"]) for row in rejected] == [
        ("payment", "duplicate_payment_id", "2")  # header is data line 1
    ]
    aging = read_rows(out, "aging_buckets.csv")
    by_id = {row["invoice_id"]: row for row in aging}
    assert by_id["E1"]["paid_cents"] == "600.00"
    assert by_id["E1"]["outstanding_cents"] == "600.00"


def test_duplicate_detection_ignores_malformed_twins(run_aging) -> None:
    # The duplicate pass only sees otherwise-valid rows: a twin that is
    # itself malformed keeps its row-level reason, and the valid invoice
    # with the same id is not collateral damage.
    invoices = [
        invoice("D2", "2026-09-01", 50000, issued="2026-08-01"),
        ["D2", "C9", "Broken Inc", "2026-08-20", "2026-09-15", "not-a-number"],
    ]
    payments = []

    out = run_aging(invoices, payments)

    rejected = {(row["source"], row["reason"]) for row in read_rows(out, "rejected_rows.csv")}
    assert rejected == {("invoice", "unparseable_amount")}
    with open(out / "collections_report.md", encoding="utf-8") as handle:
        report = handle.read()
    assert "invoiced | 50,000" in report  # 50000 cents


def test_first_problem_wins_on_a_multi_reason_row(run_aging) -> None:
    # The CASE order in staging.sql documents "first problem wins"; a row
    # that is both unreadable (blank id) and has a negative amount is
    # reported under exactly one reason.
    invoices = [["", "C8", "Who Co", "2026-08-01", "2026-09-01", -500]]
    out = run_aging(invoices, [])
    rejected = read_rows(out, "rejected_rows.csv")
    assert [(row["source"], row["reason"]) for row in rejected] == [("invoice", "blank_invoice_id")]


def test_clean_data_finds_nothing_and_exits_zero(tmp_path) -> None:
    # The exit-2 path is only for findings; on a clean run --fail-on-findings
    # must return 0 (the smoke check that a scheduler needs to trust the code).
    invoices = [invoice("Z1", "2026-11-30", 10000, issued="2026-09-01")]
    payments = [payment("PZ1", "Z1", "2026-10-10", 10000)]
    invoices_csv = write_csv(tmp_path / "invoices.csv", INVOICE_HEADER, invoices)
    payments_csv = write_csv(tmp_path / "payments.csv", PAYMENT_HEADER, payments)
    assert (
        main(
            [
                "--invoices",
                str(invoices_csv),
                "--payments",
                str(payments_csv),
                "--out",
                str(tmp_path / "out"),
                "--fail-on-findings",
            ]
        )
        == 0
    )


def test_header_only_inputs_run_clean(run_aging) -> None:
    # No rows at all is a valid (if useless) input: conservation holds by
    # empty sums and every output file exists.
    out = run_aging([], [])
    for filename in (
        "aging_buckets.csv",
        "dunning_states.csv",
        "findings.csv",
        "rejected_rows.csv",
        "duplicate_payment_candidates.csv",
        "monthly_collections.csv",
    ):
        assert read_rows(out, filename) == []
    with open(out / "collections_report.md", encoding="utf-8") as handle:
        assert "invoiced | 0" in handle.read()


def test_monthly_delta_spans_a_gap_month(run_aging) -> None:
    # A month with no payments for a method does not produce a row; the
    # next month's delta is computed against the previous month WITH data.
    # This documents the known limitation rather than inventing a month spine.
    invoices = [invoice("M1", "2027-12-01", 30000, issued="2025-12-01")]
    payments = [
        payment("PM1", "M1", "2026-01-05", 10000, "SPEI"),
        payment("PM2", "M1", "2026-03-05", 20000, "SPEI"),
    ]
    rows = read_rows(run_aging(invoices, payments), "monthly_collections.csv")
    months = [row["month"][:7] for row in rows]
    assert months == ["2026-01", "2026-03"]  # no invented 2026-02 row
    march_row = [row for row in rows if row["month"][:7] == "2026-03"][0]
    # Feb is missing, so March's delta is really Jan -> March (20K - 10K).
    assert march_row["delta_prior_month_cents"] == "100.00"


def test_bad_as_of_in_library_call_raises_data_error() -> None:
    # Library callers get the package's failure type, not a bare ValueError.
    with pytest.raises(AgingDataError):
        run_pipeline(
            invoices_path="whatever.csv",
            payments_path="whatever.csv",
            out_dir="out",
            as_of="30-09-2026",
        )
