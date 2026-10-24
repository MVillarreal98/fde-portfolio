# Changelog

All notable changes to the Collections Aging SQL project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-10-24

### Added
- Duplicate-id rejection in staging: a repeated `invoice_id` or `payment_id`
  is rejected as `duplicate_invoice_id` / `duplicate_payment_id` after its
  first occurrence, so amended or double-entered rows cannot inflate the
  money (a repeated id used to inflate invoiced cash silently).
- Uniqueness identity in the conservation check (ids are distinct in the
  clean pools), independent of the SQL pass.
- Tests: duplicate ids (invoice and payment), duplicate detection ignoring
  malformed twins, first-problem-wins ordering, header-only inputs, clean
  run with `--fail-on-findings` (exit 0) and a month gap in the monthly
  series (documented behaviour).

### Changed
- Exit code for a bad `--as-of` is now 4; 2 means findings only.
- FIFO application ties break by file line order before `payment_id`, so
  text ordering of ids no longer decides payment order.

### Fixed
- `collections_report.md` is written with the same line endings on every
  platform (written as bytes), so its golden test passes on a fresh Windows
  clone too; the file only ever differed by CRLF there.

## [1.0.0] - 2026-10-23

### Added
- DuckDB SQL pipeline over two CSV inputs (invoices, payments), as of a fixed
  reference date (`--as-of`, default 2026-09-30):
  - `staging.sql`: reads every column as text, casts defensively and splits
    each row into a clean temp table or `rejected_rows.csv` with one reason
    (blank identifiers, unparseable dates or amounts, negative
    amounts, future payments, due date before issue date).
  - `aging_buckets.sql`: one row per open invoice with the bucket
    (current / 1-30 / 31-60 / 61-90 / 91-plus) counted from the policy due
    date.
  - `dunning_states.sql`: one dunning stage per open invoice
    (pre_dunning, D3_reminder, D15_second_notice, D35_final_notice,
    D60_collections); stages only escalate and a D60 row has no next action.
  - `duplicate_payment_candidates.sql`: pairs of payments with the same
    customer and amount within a 7-day window (heuristic candidates, not
    verdicts).
  - `monthly_collections.sql`: gross/applied/unapplied cash per month and
    payment method, with a running total and a month-over-month delta.
  - `findings.sql`: orphan payments (unknown invoice) and overpayments
    (cash above the invoice total).
- FIFO cash application in SQL (`t_applied`): each payment is applied only up
  to what the invoice still owed when it arrived; the surplus is unapplied
  cash in its own column, never part of outstanding money.
- Conservation checks in the runner: raw rows = valid + rejected per source
  and invoiced cents = applied + outstanding; any failure stops the run
  (exit 1).
- CLI (`collections-aging`) with `--invoices`, `--payments`, `--out`,
  `--as-of`, `--fail-on-findings` (exit 2 for schedulers), `--log-level`,
  `--version`.
- Demo data with open invoices in every aging bucket (1, 3, 10, 30, 45, 46,
  58, 76, 91, 97 days past due) plus the invalid row that exercises each
  rejection reason (documented in `data/Dictionary.md`).
- Deterministic outputs (fixed sort order, `\n` line endings in the CSV files,
  cents shown as exact decimals); the committed `sample_output/` is what the
  CLI produces.
- Tests: golden tests that diff `sample_output/` against a fresh run, rule
  tests with fixture CSVs, CLI exit-code tests and packaging tests.
