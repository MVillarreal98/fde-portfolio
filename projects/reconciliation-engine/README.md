# Reconciliation Engine

**Problem → Tool → Impact:** Financial and operational teams that settle high retail
payment volumes (cash networks like OXXO, bank transfers like SPEI, card rails) must
prove daily that *what the operating system recorded* matches *what billing and
settlement actually paid*. Do it by hand and you audit filter by filter for hours —
and still miss edge cases. This engine does it in one run.

## What it does

Takes **two data sources** — an operational ledger and a billing/settlement file —
and produces an executive reconciliation report:

1. **Clean** — normalizes IDs, amounts, currencies and timestamps from both sources.
2. **Cross-match** — joins records by transaction reference and compares amounts
   within a configurable cent-level tolerance.
3. **Detect anomalies**
   - 🔁 **Duplicate settlements** — the same transaction settled / invoiced more than once.
   - 💸 **Amount discrepancies** — settled ≠ recorded (beyond tolerance).
   - 🧟 **Orphaned transactions** — recorded in ops but never settled (revenue leakage),
     or settled but never recorded (phantom revenue).
   - ⚠️ **Duplicate ops entries** — the same charge captured twice in the system of record.
4. **Report** — writes a human-readable executive summary (Markdown) plus machine
   readable anomaly exports (CSV) ready for the finance team.

## Architecture

```
data/ops_transactions.csv ─┐
                           ├─► loaders ─► cleaning ─► matching ─► anomalies ─► report
data/billing_statements.csv┘                                          (rules layer)
```

`src/reconciliation/` is fully modular:

| Module | Responsibility |
|---|---|
| `loaders.py` | Confidence-checked CSV ingestion, expected-column validation |
| `cleaning.py` | ID normalization, amount rounding to cents, dtype enforcement |
| `matching.py` | Cross-source joining strategy (group by reference, sum, compare) |
| `anomalies.py` | The four detection rules — pure functions, independently testable |
| `report.py` | Markdown + CSV export of the executive report |
| `config.py` | Tolerances, expected schemas, paths |

## Run it

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
python run_reconciliation.py
```

Output:

```
output/reconciliation_report.md   ← executive summary for the finance lead
output/anomalies_amount.csv       ← every failing rule, one file per rule
output/anomalies_duplicates.csv
output/anomalies_orphans.csv
```

A full run on the bundled demo data is committed under [`sample_output/`](sample_output/reconciliation_report.md)
(4 rules fired, 8 flagged rows, net difference $2,363.00) so reviewers can read the
real artifact without running anything.

## Real-world basis

Implemented against the daily reality of auditing **+240 invoices per day** at a
logistics/transport operation, where settlement runs must be defended line by line
to carriers and clients — the exact discipline a payment platform like Spin
applies across OXXO cash deposits, SPEI transfers and card settlements.
