# Changelog

All notable changes to the Reconciliation Engine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.0] - 2026-10-22

Correctness release after a review that ran 16 edge cases against v1.0.0.
Every defect below has a regression test (`tests/test_regression_probes.py`).

### Fixed
- `pip install -e .` followed by `reconcile` failed with `ImportError: tabulate`:
  tabulate (and numpy, duckdb) are now declared in `pyproject.toml`, and a test
  checks that every runtime import is a declared dependency.
- IDs were read as numbers: `00123` matched `123`, and one blank reference
  turned `1001` into `1001.0`, making every transaction an orphan. All columns
  are now read as text.
- Amounts with thousands separators (`1,250.00`) were dropped silently and their
  settlement reported as phantom revenue. Money is now parsed from text into
  integer cents (no float); anything unparseable is rejected with a reason.
- Rows with a blank ID/reference or a bad amount disappeared without trace (with
  pandas 3, a 500.00 settlement vanished from the report). They now go to
  `rejected_rows.csv`, and the report shows the count and amount per source.
- A duplicated `transaction_id` in ops doubled the settled total in the report
  (200.00 reported for 100.00 settled). Both sides are now aggregated before a
  validated one-to-one join; repeated IDs get their own rule.
- Presence on each side was inferred from `amount > 0`, so negative amounts
  (refunds) were invisible and a 0.00 charge was called "settlement without ops
  record". Presence now comes from the join itself.
- `status` was case-sensitive (`Refunded` counted as revenue leakage).
- A cancelled or refunded charge that settled in full produced no finding.
- Different currencies on each side produced no finding; the report printed a
  hard-coded `MXN`.
- A split settlement (50 + 50 for a 100 charge) was flagged as a duplicate, and
  a double settlement was counted under two rules.
- The duplicate-charge heuristic (same merchant + amount + day) produced 154,095
  false groups on 1,000,000 unique transactions. It now requires the same
  channel, a time window, and a group with fewer settlements than captures:
  0 groups on that benchmark, 1,244 when 1% of transactions never settle
  (measured with `scripts/benchmark.py`, see README).
- A negative `--tolerance` was accepted and turned exact matches into
  mismatches; tolerance must now be >= 0 and a whole number of cents.
- Removed a no-op assignment in `anomalies.py` that emitted
  `SettingWithCopyWarning`, and the `path: pd` annotation in `loaders.py`.
- README listed output files that the code never wrote, and the 1.0.0 entry
  below claimed an exact-match test that did not exist (entry corrected).

### Added
- DuckDB SQL engine (`--engine sql`): `sql/matched.sql` (CTEs, FULL OUTER JOIN,
  window functions) and one SQL file per rule. Parity tests require identical
  findings to the pandas engine on the demo data, 15 edge cases and 3 seeded
  random datasets (3 window settings each).
- Conservation checks: rows and cents read = processed + rejected per source,
  and the matched table must carry every processed row and cent; otherwise the
  run stops with `ReconciliationIntegrityError` (exit 1).
- Rules `currency_mismatch`, `settled_but_cancelled`, `duplicate_ops_ids`.
- Report: input-integrity table, gross difference, status per reference,
  currencies present, rejected rows.
- CLI: `--engine`, `--fail-on-findings` (exit 2), `--duplicate-window-minutes`,
  `--log-level`, `--version`, help text for every option; exit 1 with a single
  log line on data errors.
- `scripts/benchmark.py` (synthetic data, reproducible timings).
- Tests: 171 (from 3), including regression, parity, CLI, golden and packaging
  tests; measured statement and branch coverage of the Python package 100% on
  pandas 2.3.3 and 3.1.0 (coverage gate at 85%). `[dev]` extra with pytest,
  pytest-cov, ruff and mypy.

### Changed
- `aggregate_billing` is vectorized: 3.85 s → 0.09 s at 100,000 rows; load to
  rules 4.13 s → 0.86 s at 100k and 42.4 s → 9.0 s at 1M (Ryzen 5 5600X,
  pandas 3.1.0; see README for the method).
- Library code logs through `logging` instead of `print`.
- `--ops` and `--billing` are required (defaults used to depend on the working
  directory); `run_reconciliation.py` still runs the demo from any directory.
- Every rule writes its CSV on every run (header only when it did not fire);
  CSV amounts are written as exact decimals (`1250.00`).
- Rule `duplicate_ops_entries` renamed `duplicate_charge_candidates`.
- Only the columns the rules use are required; `settled_at` and
  `processor_fee` are accepted and ignored.
- Demo data: added T025–T027 and S026–S028 to exercise the new rules and the
  rejected-rows path (documented in `data/Dictionary.md`).

### Removed
- `requirements-dev.txt` (use `pip install -e ".[dev]"`).
- Unverifiable claims from the README: manual audits "for hours" replaced "in
  one run", "+240 invoices per day" presented as the tool's basis, and the
  pitch aimed at a specific employer. Demo figures are labeled synthetic.

## [1.0.0] - 2026-10-22
### Added
- Cross-source matching engine (ops ledger vs billing/settlement exports)
- Four deterministic anomaly rules: duplicate settlements, amount mismatches,
  orphaned one-sided records, duplicate same-day ops charges
- Executive Markdown report plus per-rule CSV exports
- Schema-validated CSV ingestion with fail-fast behavior
- Unit tests for the duplicate-settlement, mismatch and orphan rules
- Packaging: console script `reconcile`; dev tooling (ruff, mypy, pre-commit)
