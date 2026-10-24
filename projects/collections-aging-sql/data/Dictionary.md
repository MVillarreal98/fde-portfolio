# Data dictionary (synthetic demo data)

All data in `data/` is synthetic and was written for this demo. Names are
invented; amounts are integer cents of a fictional MXN; dates are ISO
`YYYY-MM-DD`. The demo "as of" date is 2026-09-30.

## `invoices.csv`

| column | type | meaning |
|---|---|---|
| `invoice_id` | text | invoice identifier, unit of the aging report |
| `customer_id` | text | synthetic customer key (`C001`..`C005`) |
| `customer_name` | text | invented retail-ish customer name |
| `issued_date` | date | invoice issue date |
| `due_date` | date | policy due date; aging counts days past this date |
| `amount_cents` | integer cents | invoiced amount (never negative when valid) |

## `payments.csv`

| column | type | meaning |
|---|---|---|
| `payment_id` | text | payment identifier |
| `invoice_id` | text | invoice the cash should be applied to; blank is invalid |
| `paid_date` | date | payment receipt date; after the as-of date is rejected |
| `amount_cents` | integer cents | payment amount (never negative when valid) |
| `method` | text | `OXXO` (cash), `SPEI` (transfer) or `CARD` |

## Planted rows and why they exist

Valid rows `INV-001`..`INV-017` and `PAY-001`..`PAY-010` cover the behaviors
the report shows, on purpose:

- Unpaid invoices on every aging boundary: not due yet (`INV-001`, `INV-008`,
  `INV-011`, `INV-016`), exactly 1 day (`INV-015`), 3 days (`INV-007`),
  10 (`INV-002`), exactly 30 (`INV-005`), 45/46/58 (`INV-009`, `INV-017`,
  `INV-012`), 76 (`INV-003`), exactly 91 (`INV-004`) and 97 (`INV-014`).
- FIFO cash application with two payments against one invoice
  (`INV-009`: 100,500 + 90,000 of the 220,500 invoiced).
- A double payment: two payments of the same amount on the same day against
  `INV-006`; the second leaves unapplied cash and forms a duplicate-payment
  candidate pair with the first.
- Cash above the invoice total (`INV-010`: full payment plus an extra 4,000)
  that becomes an overpayment finding.
- A payment received the day before the due date that closes the invoice in
  full (`INV-013`).
- A payment referencing an unknown invoice (`PAY-010` → `INV-999`):
  an orphan-payment finding, not a rejected row.

The `9xx` rows are invalid on purpose and must land in `rejected_rows.csv`
with one of these reasons:

| row | reason |
|---|---|
| `INV-900` (`abc`) | `unparseable_amount` |
| `INV-901` (`-10000`) | `negative_amount` |
| `INV-902` (blank due) | `blank_due_date` |
| `INV-903` (due before issue) | `due_before_issue` |
| `PAY-901` (blank invoice) | `blank_invoice_ref` |
| `PAY-902` (`2026-13-40`) | `unparseable_payment_date` |
| `PAY-903` (`-5000`) | `negative_amount` |
| `PAY-904` (2026-10-05, after as-of) | `future_payment` |

The remaining reasons (`blank_invoice_id`, `blank_amount`, `blank_issued_date`,
`unparseable_issued_date`, `unparseable_due_date`, `blank_payment_id`,
`blank_paid_date`, `unparseable_amount`) have no row in the demo files; the
test fixtures plant one example of each.
