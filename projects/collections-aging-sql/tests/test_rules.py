"""Rule tests: every SQL artifact exercised on small, hand-checkable fixtures."""

from __future__ import annotations

from conftest import invoice, payment, read_rows


def test_aging_bucket_boundaries(run_aging) -> None:
    invoices = [
        invoice("B1", "2026-10-10", 1000),  # not due yet
        invoice("B2", "2026-09-30", 1000),  # exactly as-of -> past due 0 -> current
        invoice("B3", "2026-09-29", 1000),  # 1 day past due
        invoice("B4", "2026-08-31", 1000),  # exactly 30 days
        invoice("B5", "2026-08-30", 1000),  # 31 days
        invoice("B6", "2026-07-02", 1000, issued="2026-06-01"),  # exactly 90 days
        invoice("B7", "2026-07-01", 1000, issued="2026-06-01"),  # 91 days
        invoice("B8", "2026-08-30", 900),  # partially paid, 31 days
        invoice("B9", "2026-08-10", 750),  # fully paid: must not appear
    ]
    payments = [payment("PB8", "B8", "2026-08-25", 600), payment("PB9", "B9", "2026-09-01", 750)]

    rows = read_rows(run_aging(invoices, payments), "aging_buckets.csv")
    by_id = {row["invoice_id"]: row for row in rows}

    assert set(by_id) == {"B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"}
    assert by_id["B1"]["aging_bucket"] == "current"
    assert by_id["B2"]["aging_bucket"] == "current"
    assert by_id["B3"]["aging_bucket"] == "1-30"
    assert by_id["B4"]["aging_bucket"] == "1-30"
    assert by_id["B5"]["aging_bucket"] == "31-60"
    assert by_id["B6"]["aging_bucket"] == "61-90"
    assert by_id["B7"]["aging_bucket"] == "91-plus"
    assert by_id["B8"]["aging_bucket"] == "31-60"
    assert by_id["B8"]["outstanding_cents"] == "3.00"
    assert by_id["B8"]["paid_cents"] == "6.00"


def test_fifo_application_and_overpayment(run_aging) -> None:
    invoices = [invoice("F1", "2026-09-01", 220500)]
    payments = [
        payment("PA", "F1", "2026-08-20", 100500, "SPEI"),
        payment("PB", "F1", "2026-09-05", 90000, "OXXO"),
        payment("PC", "F1", "2026-09-28", 50000, "OXXO"),
    ]

    out = run_aging(invoices, payments)

    # 100,500 + 90,000 fit inside the invoice; the third payment only partially
    # applies and 20,000 stays unapplied -> overpayment finding, no aging row.
    assert read_rows(out, "aging_buckets.csv") == []
    findings = read_rows(out, "findings.csv")
    assert findings == [
        {
            "code": "overpayment",
            "reference": "F1",
            "detail": "unapplied_cash_cents=20000",
        }
    ]


def test_cash_above_invoice_total_is_not_outstanding(run_aging) -> None:
    invoices = [invoice("G1", "2026-07-24", 85000, issued="2026-06-20")]
    payments = [
        payment("PG1", "G1", "2026-07-30", 85000, "SPEI"),
        payment("PG2", "G1", "2026-08-02", 4000, "OXXO"),
    ]

    out = run_aging(invoices, payments)

    assert read_rows(out, "aging_buckets.csv") == []
    assert [{"code": "overpayment", "reference": "G1", "detail": "unapplied_cash_cents=4000"}] == (
        read_rows(out, "findings.csv")
    )
    monthly = read_rows(out, "monthly_collections.csv")
    assert monthly == [
        {
            "month": "2026-07-01",
            "method": "SPEI",
            "gross_cents": "850.00",
            "applied_cents": "850.00",
            "unapplied_cents": "0.00",
            "delta_prior_month_cents": "",
            "running_gross_cents": "850.00",
        },
        {
            "month": "2026-08-01",
            "method": "OXXO",
            "gross_cents": "40.00",
            "applied_cents": "0.00",
            "unapplied_cents": "40.00",
            "delta_prior_month_cents": "",
            "running_gross_cents": "40.00",
        },
    ]


def test_dunning_stages_and_next_action(run_aging) -> None:
    invoices = [
        invoice("D60", "2026-03-02", 1000, issued="2026-02-01"),  # 211 days past due
        invoice("D35", "2026-08-09", 1000),  # 52 days
        invoice("D15", "2026-08-31", 1000),  # 30 days
        invoice("D3", "2026-09-27", 1000),  # 3 days
        invoice("PRE1", "2026-09-29", 1000),  # 1 day
        invoice("PRE0", "2026-09-30", 1000),  # due on the as-of date
    ]

    rows = read_rows(run_aging(invoices, []), "dunning_states.csv")
    by_id = {row["invoice_id"]: row for row in rows}

    assert by_id["D60"]["stage"] == "D60_collections"
    assert by_id["D60"]["next_action_date"] == ""  # there is nothing after D60
    assert by_id["D35"]["stage"] == "D35_final_notice"
    assert by_id["D35"]["next_action_date"] == "2026-10-08"
    assert by_id["D15"]["stage"] == "D15_second_notice"
    assert by_id["D15"]["next_action_date"] == "2026-10-05"
    assert by_id["D3"]["stage"] == "D3_reminder"
    assert by_id["D3"]["next_action_date"] == "2026-10-12"
    assert by_id["PRE1"]["stage"] == "pre_dunning"
    assert by_id["PRE1"]["next_action_date"] == "2026-10-02"
    assert by_id["PRE0"]["stage"] == "pre_dunning"
    assert by_id["PRE0"]["next_action_date"] == "2026-10-03"
    # most overdue first, then invoice id
    assert [row["invoice_id"] for row in rows] == ["D60", "D35", "D15", "D3", "PRE1", "PRE0"]


def test_duplicate_payment_candidates_window(run_aging) -> None:
    invoices = [
        invoice("P1", "2026-09-15", 1000, customer="C1"),
        invoice("P2", "2026-09-15", 1000, customer="C1"),
        invoice("P3", "2026-09-15", 700, customer="C2"),
        invoice("P4", "2026-09-15", 700, customer="C3"),
        invoice("P5", "2026-09-15", 500, customer="C1"),
    ]
    payments = [
        payment("PA", "P1", "2026-09-20", 1000),
        payment("PB", "P2", "2026-09-27", 1000),  # 7 days apart -> candidate
        payment("PC", "P3", "2026-09-20", 700),
        payment("PD", "P4", "2026-09-27", 700),  # different customers -> not
        payment("PF", "P1", "2026-09-28", 500),  # 8 days from PE -> not
        payment("PE", "P5", "2026-09-20", 500),
    ]

    rows = read_rows(run_aging(invoices, payments), "duplicate_payment_candidates.csv")

    assert rows == [
        {
            "payment_id_a": "PA",
            "payment_id_b": "PB",
            "customer_id": "C1",
            "amount_cents": "10.00",
            "paid_date_a": "2026-09-20",
            "paid_date_b": "2026-09-27",
            "days_apart": "7",
        }
    ]


def test_orphan_payment_is_a_finding_not_a_rejection(run_aging) -> None:
    invoices = [invoice("H1", "2026-09-15", 1000)]
    payments = [payment("PH", "H1", "2026-09-10", 500), payment("PX", "INV-999", "2026-09-12", 300)]

    out = run_aging(invoices, payments)
    rows = read_rows(out, "aging_buckets.csv")

    # the orphan cash never reaches the aging money
    assert rows[0]["paid_cents"] == "5.00"
    assert rows[0]["outstanding_cents"] == "5.00"
    assert [
        {"code": "orphan_payment", "reference": "PX", "detail": "unknown_invoice_id=INV-999"}
    ] == (read_rows(out, "findings.csv"))
    # applied-only collections exclude the orphan payment
    assert len(read_rows(out, "monthly_collections.csv")) == 1


REJECTED_INVOICES = [
    ["", "C1", "Demo Inc", "2026-08-01", "2026-08-15", 1000],  # blank_invoice_id
    ["R1", "C1", "Demo Inc", "2026-08-02", "2026-08-16", ""],  # blank_amount
    ["R2", "C1", "Demo Inc", "2026-08-02", "2026-08-16", "abc"],  # unparseable_amount
    ["R3", "C1", "Demo Inc", "2026-08-03", "2026-08-17", -5000],  # negative_amount
    ["R4", "C1", "Demo Inc", "", "2026-08-18", 1000],  # blank_issued_date
    ["R5", "C1", "Demo Inc", "not-a-date", "2026-08-19", 1000],
    ["R6", "C1", "Demo Inc", "2026-08-04", "", 1000],  # blank_due_date
    ["R7", "C1", "Demo Inc", "2026-08-05", "2026-13-40", 1000],
    ["R8", "C1", "Demo Inc", "2026-08-10", "2026-08-01", 1000],  # due_before_issue
]
INVOICE_REASONS = [
    "blank_invoice_id",
    "blank_amount",
    "unparseable_amount",
    "negative_amount",
    "blank_issued_date",
    "unparseable_issued_date",
    "blank_due_date",
    "unparseable_due_date",
    "due_before_issue",
]


def test_invoice_rejections_land_with_a_reason(run_aging) -> None:
    invoices = [invoice("V1", "2026-08-15", 1000), *REJECTED_INVOICES]

    out = run_aging(invoices, [])
    rows = read_rows(out, "rejected_rows.csv")

    # line_no counts data rows in the source file: V1 is line 1, the blank id
    # line 2, and so on up to R8 on line 10.
    assert rows == [
        {"source": "invoice", "reference": reference, "line_no": str(number), "reason": reason}
        for number, (reference, reason) in enumerate(
            zip(["", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"], INVOICE_REASONS, strict=True),
            start=2,
        )
    ]
    # the single valid invoice still ages normally; no rejected row leaks in
    aging = read_rows(out, "aging_buckets.csv")
    assert [row["invoice_id"] for row in aging] == ["V1"]


def test_payment_rejections_land_with_a_reason(run_aging) -> None:
    invoices = [invoice("V1", "2026-09-15", 1000)]
    payments = [
        ["", "V1", "2026-09-10", 100, "OXXO"],  # blank_payment_id
        ["Q1", "V1", "2026-09-11", "", "OXXO"],  # blank_amount
        ["Q2", "V1", "2026-09-12", "abc", "OXXO"],  # unparseable_amount
        ["Q3", "V1", "2026-09-13", -5000, "OXXO"],
        ["Q4", "", "2026-09-14", 100, "OXXO"],  # blank invoice reference
        ["Q5", "V1", "", 100, "OXXO"],
        ["Q6", "V1", "2026-13-40", 100, "OXXO"],
        ["Q7", "V1", "2026-10-05", 100, "OXXO"],  # after the as-of date
        payment("OK", "V1", "2026-09-10", 100),
    ]

    out = run_aging(invoices, payments)
    rows = read_rows(out, "rejected_rows.csv")

    assert rows == [
        {"source": "payment", "reference": reference, "line_no": str(number), "reason": reason}
        for number, (reference, reason) in enumerate(
            zip(
                ["", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"],
                [
                    "blank_payment_id",
                    "blank_amount",
                    "unparseable_amount",
                    "negative_amount",
                    "blank_invoice_ref",
                    "blank_paid_date",
                    "unparseable_payment_date",
                    "future_payment",
                ],
                strict=True,
            ),
            start=1,
        )
    ]
    aging = read_rows(out, "aging_buckets.csv")
    assert aging[0]["paid_cents"] == "1.00"


def test_as_of_date_parameter_is_respected(run_aging) -> None:
    invoices = [invoice("Z1", "2026-10-01", 1000)]
    payments = [payment("PZ1", "Z1", "2026-10-05", 1000)]

    # with the default as-of the payment is still future-dated and rejected
    out = run_aging(invoices, payments)
    assert [row["reason"] for row in read_rows(out, "rejected_rows.csv")] == ["future_payment"]
    assert read_rows(out, "aging_buckets.csv")[0]["days_past_due"] == "0"

    out = run_aging(invoices, payments, as_of="2026-10-15")
    assert read_rows(out, "rejected_rows.csv") == []
    assert read_rows(out, "aging_buckets.csv") == []
