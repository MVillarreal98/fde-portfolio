"""Review-r2 regressions: integer-literal amounts, payments identity,
orphan detail."""

from __future__ import annotations

from conftest import invoice, payment, read_rows


def test_non_integer_cents_never_round_into_ages(run_aging) -> None:
    # TRY_CAST(... AS BIGINT) would round 1500.50 to 1501 cents and accept
    # '1e3' / '1_000': a pesos figure as cents saves 100x - must be rejected
    # with the text intact.
    invoices = [
        invoice("X1", "2026-09-01", 100_000, issued="2026-08-01"),
        # pesos with cents written as text: the BIGINT cast would round it
        ["X2", "C1", "Demo Inc", "2026-08-01", "2026-09-01", "1500.50"],
    ]
    out = run_aging(invoices, [])
    rejected = read_rows(out, "rejected_rows.csv")
    assert [(row["source"], row["reason"]) for row in rejected] == [
        ("invoice", "unparseable_amount")
    ]
    with open(out / "collections_report.md", encoding="utf-8") as handle:
        assert "invoiced | 100,000" in handle.read()


def test_exponent_and_underscore_are_not_integer_literals(run_aging) -> None:
    invoices = [
        invoice("X3", "2026-09-01", 1000, issued="2026-08-01"),
        ["X4", "C9", "Sinistra Ltd", "2026-09-01", "2026-09-15", "1e3"],
        ["X5", "C9", "Sinistra Ltd", "2026-09-01", "2026-09-15", "1_000"],
    ]
    out = run_aging(invoices, [])
    reasons = [row["reason"] for row in read_rows(out, "rejected_rows.csv")]
    assert reasons == ["unparseable_amount", "unparseable_amount"]
    with open(out / "collections_report.md", encoding="utf-8") as handle:
        assert "invoiced | 1,000" in handle.read()


def test_orphan_payment_on_rejected_invoice_details_the_reason(run_aging) -> None:
    # The invoice amount is unparseable, so a payment referencing it lands
    # as orphan cash: the detail names the staging rejection, not "unknown".
    invoices = [
        ["X6", "C9", "Broken Ltd", "2026-09-01", "2026-09-15", "150.0"],
    ]
    payments = [payment("PX1", "X6", "2026-09-10", 15000)]
    out = run_aging(invoices, payments)
    findings = read_rows(out, "findings.csv")
    assert findings == [
        {
            "code": "orphan_payment",
            "reference": "PX1",
            "detail": "invoice_rejected_at_staging=X6",
        }
    ]


def test_payments_identity_holds_with_orphan_and_unapplied(run_aging) -> None:
    # 12,500 ledger: 10,000 applied, 2,000 unapplied drop, 500 orphan. If a
    # future change fans out the application join, this invariant aborts it.
    invoices = [
        invoice("Y1", "2026-09-20", 1000000, issued="2026-08-01"),
        invoice("Y2", "2026-07-24", 85000, issued="2026-06-20"),
    ]
    payments = [
        payment("PY1", "Y1", "2026-08-20", 1000000),
        payment("PY2", "Y2", "2026-07-30", 85000),
        payment("PY3", "Y2", "2026-08-02", 2000),
        payment("PY9", "GHOST-1", "2026-08-02", 500),
    ]
    out = run_aging(invoices, payments)
    findings = read_rows(out, "findings.csv")
    detail = [f["detail"] for f in findings if f["reference"] == "PY9"]
    assert detail == ["unknown_invoice_id=GHOST-1"]
