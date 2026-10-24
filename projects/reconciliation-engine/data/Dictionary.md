# Data Dictionary — sample datasets

Both demo datasets are **synthetic**: written by hand to reproduce the anomaly
classes the engine detects. They contain no real transactions and no personal
data. Every column is read as text; the engine types amounts and timestamps
itself and lists any row it cannot use in `rejected_rows.csv`.

## `data/ops_transactions.csv` — operational ledger (system of record)
| Column | Type | Meaning |
|---|---|---|
| `transaction_id` | text | Charge identifier, the reconciliation key. Compared exactly after trimming and upper-casing (`00123` ≠ `123`). Blank → rejected. |
| `merchant` | text | Merchant/store name. Used by the duplicate-charge heuristic. |
| `channel` | text | Payment rail: `OXXO` (cash), `SPEI` (bank transfer), `CARD`. |
| `amount` | money | Amount captured. Optional sign, optional thousands separators (`1,250.00`). Negative = refund/reversal recorded as its own movement. Unparseable → rejected. |
| `currency` | text | ISO code (MXN in most demo rows). Compared against the billing side. |
| `status` | text | `captured`, `refunded`, `cancelled`/`canceled`, `void`; case-insensitive. See status semantics below. |
| `recorded_at` | timestamp | When the system recorded the charge. Unparseable values do not reject the row; it only stays out of the duplicate-charge heuristic. |

## `data/billing_statements.csv` — billing/settlement export
| Column | Type | Meaning |
|---|---|---|
| `statement_id` | text | Settlement line identifier (`S001`–…). |
| `transaction_ref` | text | **Foreign key** to `ops_transactions.transaction_id`. Blank → rejected. |
| `settlement_amount` | money | Amount the processor settled for that line (same format rules as `amount`). |
| `currency` | text | ISO code. |
| `settled_at` | date | Settlement date. Accepted, not used by any rule (see README limitations). |
| `processor_fee` | money | Fee charged by the processor. Accepted, not used: settlements are compared gross. |

## Status semantics
`refunded`, `cancelled`/`canceled` and `void` describe a charge that was
reversed, so its **expected net settlement is zero**: either it never settles
(status `cancelled_not_settled`, not a finding) or it settles and is reversed
in the same file (`+X` and `-X`, status `matched`). A reversed charge whose
settlements do not net to zero is reported as `settled_but_cancelled`.

## Planted anomalies (for the demo and the golden test)
| Class | Where | Story |
|---|---|---|
| Duplicate settlement | `S007`+`S008` → `T007` | Processor settled the same 3,400.00 twice. |
| Amount mismatch | `T009`, `T012`, `T018` | Under-settlements of 8.00, 10.00 and 19.00. |
| Settled but cancelled | `T011` / `S012` | Refunded in ops, yet settled +450.00 with no reversal. |
| Orphan: ops without settlement | `T013` | Recorded, never settled: possible revenue leakage. |
| Orphan + duplicate-charge candidate | `T025` | Same store, channel and amount as `T015`, 7 minutes later, never settled: likely a double capture of `T015`. |
| Orphan: settlement without ops | `T499` / `S025` | Settled but never recorded: possible phantom revenue. |
| Currency mismatch | `T027` / `S028` | Recorded in USD, settled in MXN. |
| Rejected row | `S027` | Settlement line without `transaction_ref` (500.00): listed in `rejected_rows.csv`, excluded from totals. |

Rows that look suspicious but are **not** anomalies, kept on purpose:

| Case | Where | Why it is not flagged |
|---|---|---|
| Thousands separator | `T026` (`"1,250.00"`) / `S026` | Parsed exactly and matched (v1.0.0 dropped the row and reported `S026` as phantom revenue). |
| Identical cash payments | `T005`, `T006` | Same store and amount 4 minutes apart, but each settled on its own line (`S005`, `S006`): two real payments (v1.0.0 flagged them as a duplicate). |
