# Data Dictionary — sample datasets

Both demo datasets are **synthetic**, generated to reproduce the anomaly
classes the engines detect. They contain no personal data.

## `data/ops_transactions.csv` — operational ledger (system of record)
| Column | Type | Meaning |
|---|---|---|
| `transaction_id` | string | Unique charge identifier (`T001`–`T024`). The reconciliation key. |
| `merchant` | string | Merchant/display name for the charge. |
| `channel` | enum | Payment rail: `OXXO` (cash), `SPEI` (bank transfer), `CARD`. |
| `amount` | decimal(2) | Amount captured, MXN. |
| `currency` | string | ISO currency code (MXN in the demo). |
| `status` | enum | `captured`, `refunded`, `cancelled` (refunds are expected to consent). |
| `recorded_at` | datetime | When the system recorded the charge. |

## `data/billing_statements.csv` — billing/settlement export
| Column | Type | Meaning |
|---|---|---|
| `statement_id` | string | Settlement line identifier (`S001`–…). Duplicates here duplicate billings. |
| `transaction_ref` | string | **Foreign key** to `ops_transactions.transaction_id`. |
| `settlement_amount` | decimal(2) | Amount the processor billed/settled for that transaction. |
| `currency` | string | ISO currency code. |
| `settled_at` | date | Settlement date (may lag the ops date). |
| `processor_fee` | decimal(2) | Fee charged by the processor. |

## Planted anomalies (for the demo and the tests)
| Anomaly class | Where | Story |
|---|---|---|
| Duplicate settlement | `S007`+`S008` → `T007` | Processor billed twice: $3,400 extra in the settled total. |
| Amount mismatch | `T009`, `T012`, `T018` | Under-settlements of $8.00, $10.00 and $19.00. |
| Orphan (ops without settlement) | `T013` | Recorded, never settled: possible revenue leakage. |
| Orphan (settlement without ops) | `T499`/`S025` | Settled but never recorded: possible phantom revenue. |
| Duplicate ops charge | `T005`+`T006` | Same merchant/amount/day detected as suspected duplicate capture. |
