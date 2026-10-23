# Changelog

All notable changes to the Reconciliation Engine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-10-22
### Added
- Cross-source matching engine (ops ledger vs billing/settlement exports)
- Four deterministic anomaly rules: duplicate settlements, amount mismatches,
  orphaned one-sided records, duplicate same-day ops charges
- Executive Markdown report plus per-rule CSV exports
- Schema-validated CSV ingestion with fail-fast behavior
- Unit tests covering the exact-match, mismatch and refund/orphan paths
- Packaging: console script `reconcile`; dev tooling (ruff, mypy, pre-commit)
