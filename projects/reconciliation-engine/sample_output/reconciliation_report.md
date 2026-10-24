# Reconciliation Executive Report

_Engine: pandas · tolerance 0.01 · duplicate-charge window 10 min · reconciliation-engine 2.0.0_

## Input integrity

| source   | rows read   | processed   | rejected   | rejected amount   | unparseable amounts   |
|:---------|:------------|:------------|:-----------|:------------------|:----------------------|
| ops      | 27          | 27          | 0          | $0.00             | 0                     |
| billing  | 28          | 27          | 1          | $500.00           | 0                     |

Conservation checks passed: per source, rows read = processed + rejected and the parseable amount read = processed + rejected amount; the matched table carries every processed row and cent.

## Health at a glance

- **References:** 28 (27 in ops, 26 in billing)
- **Recorded total (ops):** $19,105.76
- **Settled total (billing):** $21,393.76
- **Net difference (settled − recorded):** $2,288.00
- **Gross difference (sum of |settled − recorded| per reference):** $5,012.00
- **Currencies in input:** MXN, USD
- **References with a reconciliation finding:** 9 · **rules fired:** 6 · **flagged rows:** 10

### Status per reference

| status                | meaning                                             | references   | recorded   | settled   |
|:----------------------|:----------------------------------------------------|:-------------|:-----------|:----------|
| matched               | Recorded and settled amounts agree within tolerance | 19           | 12338.51   | 12338.51  |
| duplicate_settlement  | Same amount settled more than once                  | 1            | 3400.00    | 6800.00   |
| amount_mismatch       | Settled total differs from recorded amount          | 3            | 1492.25    | 1455.25   |
| currency_mismatch     | Currencies differ between sources                   | 1            | 100.00     | 100.00    |
| settled_but_cancelled | Reversed in ops but settlement does not net to zero | 1            | 450.00     | 450.00    |
| ops_only              | Recorded, never settled                             | 2            | 1325.00    | 0.00      |
| billing_only          | Settled, never recorded                             | 1            | 0.00       | 250.00    |

## Findings

### Duplicate Settlements (1)

Same amount settled more than once for a reference, pushing the total off the charge.

| transaction_ref   | merchant             | channel   | ops_amount   | settlement_total   | amount_difference   | settlement_count   | statement_ids   |
|:------------------|:---------------------|:----------|:-------------|:-------------------|:--------------------|:-------------------|:----------------|
| T007              | Marketplace Seller A | SPEI      | 3400.00      | 6800.00            | 3400.00             | 2                  | S007, S008      |

### Amount Mismatch (3)

Settled total differs from the recorded amount beyond tolerance.

| transaction_ref   | merchant             | channel   | ops_amount   | settlement_total   | amount_difference   |
|:------------------|:---------------------|:----------|:-------------|:-------------------|:--------------------|
| T018              | Subscription Renewal | CARD      | 199.00       | 180.00             | -19.00              |
| T012              | Convenience Store 03 | OXXO      | 512.75       | 502.75             | -10.00              |
| T009              | Marketplace Seller C | SPEI      | 780.50       | 772.50             | -8.00               |

### Currency Mismatch (1)

Ops and billing disagree on currency (or one side mixes currencies).

| transaction_ref   | merchant             | channel   | ops_currency   | settlement_currency   | ops_amount   | settlement_total   |
|:------------------|:---------------------|:----------|:---------------|:----------------------|:-------------|:-------------------|
| T027              | Subscription Renewal | CARD      | USD            | MXN                   | 100.00       | 100.00             |

### Settled But Cancelled (1)

Refunded/cancelled/void in ops, yet its settlements do not net to zero.

| transaction_ref   | merchant          | channel   | status   | ops_amount   | settlement_total   | statement_ids   |
|:------------------|:------------------|:----------|:---------|:-------------|:-------------------|:----------------|
| T011              | Refund - Seller B | SPEI      | refunded | 450.00       | 450.00             | S012            |

### Orphans (3)

One-sided records: recorded-but-never-settled or settled-but-never-recorded.

| transaction_ref   | merchant             | channel   | ops_amount   | settlement_total   | discrepancy_type                                         |
|:------------------|:---------------------|:----------|:-------------|:-------------------|:---------------------------------------------------------|
| T013              | Marketplace Seller D | SPEI      | 1250.00      | 0.00               | ops_without_settlement (possible revenue leakage)        |
| T025              | Convenience Store 04 | OXXO      | 75.00        | 0.00               | ops_without_settlement (possible revenue leakage)        |
| T499              | —                    | —         | 0.00         | 250.00             | settlement_without_ops_record (possible phantom revenue) |

### Duplicate Charge Candidates (1)

Repeated captures that look like one payment recorded twice.

| merchant             | channel   | amount   | occurrences   | settled_count   | transaction_ids   | first_recorded_at   | last_recorded_at   |
|:---------------------|:----------|:---------|:--------------|:----------------|:------------------|:--------------------|:-------------------|
| Convenience Store 04 | OXXO      | 75.00    | 2             | 1               | T015, T025        | 2025-03-01 17:45    | 2025-03-01 17:52   |


## Rejected rows (1)

Rows that could not be reconciled as read. They are excluded from the totals above and listed in full in `rejected_rows.csv`.

| source   | row_number   | transaction_ref   | statement_id   | raw_amount   | parsed_amount   | reason                  |
|:---------|:-------------|:------------------|:---------------|:-------------|:----------------|:------------------------|
| billing  | 27           |                   | S027           | 500.00       | 500.00          | missing transaction_ref |

---
_Generated by reconciliation-engine 2.0.0_
