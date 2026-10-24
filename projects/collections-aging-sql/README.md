# Collections Aging SQL

Ages every open invoice, assigns the dunning stage per policy, lists
duplicate-payment candidates and reports findings — **all business logic in
DuckDB SQL**. The Python side only stages the CSV inputs, runs the SQL files
and writes deterministic outputs.

> **Status, plainly.** This is a portfolio demo. The datasets in `data/` are
> synthetic and were written for the demo. There are no users, no production
> deployment and no measured business impact. Every number in this README is a
> test count or a measurement of this repo's own demo run; the data and
> methods are documented here and in each SQL file.

## Problem → root cause → solution → how it would be measured

- **Problem.** In collections, someone has to answer, per invoice: how much is
  still open, how late is it, which reminder or final notice must go out today,
  is that "double payment" the same charge paid twice, and does the money add
  up. Doing it by hand in a spreadsheet is where aging drifts and double
  payments hide.
- **Root causes it is built around.** Amounts parsed loosely (an `abc` amount
  vanishing from the aging without a trace), payments applied out of order or
  double-applied (cash past the invoice total being read as money still owed),
  aging counted from the issue date instead of the policy due date, rejected
  rows disappearing between tools, and a duplicate heuristic that flags every
  pair in the book.
- **Solution.** Two CSVs (invoices, payments) go through one staging pass that
  reads everything as text and casts defensively: any row that cannot be used
  gets an exact reason in `rejected_rows.csv`. Usable payments are applied FIFO
  in SQL; a payment applies only up to what the invoice still owed, and the
  surplus is unapplied cash in its own column. Aging buckets count days past
  the **due date**. Dunning stages only escalate (pre_dunning → D3 → D15 →
  D35 → D60) and off-policy cash can never lower one. Duplicate candidates are
  pairs (same customer, same amount, ≤ 7 days apart) — a reviewer queue, not a
  verdict. Before a single report is written, the runner checks two
  identities: raw rows = valid + rejected per source, and invoiced cents =
  applied + outstanding; if either fails the run stops (exit 1). The row
  identity holds by construction of the staging and is kept as a regression
  guard; the cents identity catches over-application. Neither checks the
  payment side (see Known limitations).
- **How it would be measured.** On real files, the measures would be: share of
  open invoices aged automatically, disputes avoided per period, dunning letters
  sent on the correct day, duplicate candidates confirmed over dismissed, and
  time from file arrival to a distributed call sheet. None of these has been
  measured, because there is no real data here.

## Outputs (all written on every run)

| file | one row per | notable columns |
|---|---|---|
| `aging_buckets.csv` | open invoice (outstanding > 0) | `days_past_due`, `aging_bucket` (`current` / `1-30` / `31-60` / `61-90` / `91-plus`), `outstanding_cents` |
| `dunning_states.csv` | open invoice | `stage` (`pre_dunning`…`D60_collections`), `next_action_date` (empty after D60) |
| `duplicate_payment_candidates.csv` | suspicious payment pair | `payment_id_a`/`_b`, `days_apart` |
| `monthly_collections.csv` | month × method | gross / applied / unapplied cash, delta vs prior month, running total |
| `findings.csv` | semantic problem | `orphan_payment` (unknown invoice), `overpayment` (cash above the invoice total) |
| `rejected_rows.csv` | unusable input row | exact `reason` (`blank_amount`, `unparseable_amount`, `negative_amount`, `future_payment`, `due_before_issue`, …) |
| `collections_report.md` | — | integrity table, money identity, findings |

The committed `sample_output/` is what `data/` produces; a golden test diffs
every file against a fresh run. Input amounts are integer cents, but in the
CSV outputs every `*_cents` column is formatted as pesos with two decimals
(`1550.00` is 155,000 cents); the `detail` text in `findings.csv` keeps raw
cents (`unapplied_cash_cents=75000`).

## The SQL

Everything is in
[`src/aging_sql/sql/`](src/aging_sql/sql/), one file per artifact plus the
staging pass:

- `staging.sql` — reads both CSVs with `all_varchar`, casts with `TRY_CAST`,
  and splits rejected rows by ordered `CASE` so the first problem wins. Sets
  up `t_applied`, the FIFO application table (a running `SUM() OVER
  (PARTITION BY invoice_id ORDER BY paid_date, payment_id)` against the
  invoice total).
- `aging_buckets.sql`, `dunning_states.sql` — each self-contained with its own
  balances CTE, as of a session variable (`SET VARIABLE as_of`), so a new
  reference date needs no data change.
- `duplicate_payment_candidates.sql` — a self-join on customer + amount +
  window.
- `monthly_collections.sql` — `date_trunc` month, `LAG()` per method over the
  aggregated month.
- `findings.sql`, `rejected_rows.sql` — reviewer lists.

## Run it

Tested locally on Python 3.12 with DuckDB 2.0 on Windows; the CI job runs
Python 3.12 on Ubuntu. The tests import `tomllib`, so they need Python 3.11+.

```bash
cd projects/collections-aging-sql
pip install -e ".[dev]"

# the demo, data/ -> output/ (log lines show the money identity holding)
python run_collections_aging.py

# the CLI
collections-aging --invoices data/invoices.csv --payments data/payments.csv --out output
collections-aging --invoices data/invoices.csv --payments data/payments.csv --out output --as-of 2026-09-30 --fail-on-findings

# tests, lint and types (85% branch-coverage gate is in pyproject.toml)
python -m pytest -p no:cacheprovider --cov --cov-report=term
ruff check . && ruff format --check . && mypy src
```

Exit codes: `0` clean run · `2` findings with `--fail-on-findings` (for
schedulers) · `1` unreadable inputs or a failed conservation check.

## How it is tested

25 pytest tests:

- **Golden tests** diff all seven sample-output files against a fresh run of
  the committed data, byte for byte.
- **Rule tests** plant hand-computable fixtures: invoices at the aging
  boundaries 0/1, 30/31 and 90/91 days past due plus one not yet due (the
  60/61 boundary is not tested), dunning stages at 0, 1, 3, 30, 52 and 211
  days (the exact 15, 35 and 60-day thresholds are not tested), FIFO
  application with the third payment landing partially (+ the overpayment
  finding), the duplicate
  window at 7 versus 8 days and across different customers, every rejection
  reason once, orphan payments excluded from aged money but reported as a
  finding, and `--as-of` moving rows between "future payment" and applied
  cash.
- **CLI tests** check the exit-code contract and argument handling.
- **Packaging tests** check the declared dependency set against the imports
  actually used, the console script, that the SQL files are declared as
  package data, and that `sample_output/` holds exactly the declared outputs.

## Known limitations

- Payments reference exactly one invoice. It cannot prove that unpaid cash
  was applied to the "right" invoice — `orphan_payment` only reports an
  unknown one.
- The duplicate rule is a heuristic; legitimate installments can match it, so
  the output is titled *candidates* and nothing is reversed automatically.
- Dunning and aging thresholds (3/15/35/60 days; buckets 30/60/90) are
  constants of this demo's policy, stated in the SQL, not configuration.
- Money is integer cents; there is no currency or FX column.
- Amount parsing first demands an integer literal (`-?[0-9]+`): `abc`,
  `1,500`, `1500.50`, `1e3` and `1_000` are all rejected with the raw text in
  `rejected_rows.csv`. A file with pesos instead of cents still looks valid
  (it *is* integers) - that is not detectable from the file alone.
- Repeated `invoice_id` or `payment_id` values are not rejected. A payment
  exported twice is applied twice (it can close an invoice that still owes
  money and is not listed as a duplicate candidate); a repeated invoice is
  aged twice or stops the run on the cents identity, depending on its
  payments.
- The runner has no payment-side identity (payments = applied + unapplied +
  orphan cash); on the demo data it holds when checked by hand.
- The month-over-month delta in `monthly_collections.csv` compares with the
  previous month that has data for that method, not the previous calendar
  month.
- A payment to an invoice that was rejected in staging is reported as
  `orphan_payment` (unknown invoice).
- Payment plans, promises to pay and per-customer dunning overrides are out of
  scope.

## How it was built

Built with the help of AI coding tools; design decisions, tests and
limitations are documented here, and the CHANGELOG records what changed
between versions.
