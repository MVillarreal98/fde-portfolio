# Changelog

All notable changes to the LLM Support Desk are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-10-22
### Added
- Operator web UI (stdlib HTTP server) with health badge and decision cards
- Code-owned system prompt with typed dynamic context injection
- Ollama REST client forcing protocol-level JSON output
- Fail-closed triage JSON schema (types, category whitelist, confidence range)
- Deterministic rules layer: refund autocap, low-confidence escalation,
  unauthorized-charge severity override
- Auditable keyword fallback classifier for LLM-downtime continuity
- Unit tests with fake-LLM injection (no inference needed)
- Packaging: console script `support-desk`; dev tooling (ruff, mypy, pre-commit)
