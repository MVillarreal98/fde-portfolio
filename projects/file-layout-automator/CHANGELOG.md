# Changelog

All notable changes to the Document Layout Automator are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-10-22
### Added
- WPF single-screen operator app: profile picker, source preview,
  per-line diagnostics, engineered run summary, artifact path in status bar
- Declarative layout engine (`LayoutTransformer`): per-column rules with
  requiredness, fixed widths, zero/left/right padding, regex validation
  and defaults; header-aware CSV reader honoring quoted cells
- Two built-in audited profiles: Guía Depósito (fixed-width deposit guide)
  and Carrier ASN (per-store packing totals)
- Fail-closed run: no artifact is generated while any row is rejected
- Five xunit tests covering padding, defaults, required/regex/overflow
- Packaging: solution file, .editorconfig; dev tooling (Coverlet coverage)
