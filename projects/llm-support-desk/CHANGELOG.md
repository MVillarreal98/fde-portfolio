# Changelog

All notable changes to the LLM Support Desk are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.2.0] - 2026-10-22
Fixes for the defects found in an external code review, each covered by a test.

### Security
- Operator UI no longer uses `innerHTML`: every value is rendered with
  `textContent`, and a per-response CSP nonce blocks inline event handlers. A model
  answer containing `<img onerror=...>` previously executed in the browser.
- Prompt injection: the ticket is passed as JSON-escaped data inside `<ticket_data>`
  and the system prompt marks it as untrusted. More importantly, new deterministic
  guardrails (`fraud_signal`, `exposure_above_cap`, `money_on_app_issue`, and
  unauthorized charges always escalated) cannot be lowered by any model answer.
  Previously an injected ticket closed a 4,800 MXN fraud claim without escalation.
- The schema keeps only whitelisted fields, so a model cannot set `escalated`,
  `action` or `source`.

### Fixed
- Severity is stored normalized and compared case-insensitively: `LOW`/`Low` no
  longer skipped the unauthorized-charge rule.
- The refund cap uses `max(ticket amount, model amount_at_risk)`; a model proposing
  a 25,000 refund on a 100 ticket was "first-line ready".
- `POST /api/triage` returns 400/411/413 with a JSON message for invalid JSON, wrong
  types, NaN/infinite/negative amounts, missing or oversized bodies; unexpected
  errors return a generic 500. Previously the connection dropped without a response.
- Unexpected LLM client exceptions degrade to the fallback instead of crashing.
- `/api/health` no longer calls Ollama synchronously: liveness answers from a cached
  background probe, which now also checks that the configured model is pulled (it
  used to say "connected" while every triage failed with HTTP 404).
- Default model aligned to `llama3.2:1b`; every setting is read at `Config()` time
  with a clear error for invalid values (an invalid `SUPPORT_DESK_PORT` used to
  break `import support_desk`).
- Keyword fallback: word-bounded matching ("recarga" and "disappeared" no longer
  match app keywords), fraud checked before duplicates, Spanish phrases such as "no
  reconozco" added; `payment_not_received` is refund-eligible, as the data
  dictionary already stated.
- Docker runtime image no longer contains pytest; `docker logs` now shows output
  (`PYTHONUNBUFFERED`); compose no longer blocks the desk on the model download.
- `__version__` matches the package version; `pip install -e ".[dev]"` works.

### Added
- SQLite decision log (`store.py`, `SUPPORT_DESK_DB`) with prompt hash, model,
  proposed vs final decision, rules fired and override flag; SQL metrics via
  `support-desk metrics` and `GET /api/metrics`.
- Final `action` computed by the rules (`escalate_to_human`, `first_line_refund`,
  `first_line_review`), plus `rules_applied` and `rules_override` in every decision.
- `support-desk eval`: agreement against labels for the fallback and the LLM;
  results measured with llama3.2:1b are in the README.
- Labels (`expected_category`, `must_escalate`) and 18 more synthetic tickets in
  `data/sample_tickets.csv`.
- Structured JSON logging; deterministic sampling (`temperature 0`, fixed seed).
- Tests: 133 (adversarial injection, HTTP status codes, XSS posture, persistence,
  metrics, Ollama client against a stub server, CLI); coverage 55% → 99%.

### Removed
- The demo GIF, which showed the previous UI.

## [1.1.0] - 2026-10-22
### Added
- Multi-stage `Dockerfile`: unit tests run in the `test` stage image, the
  runtime stage ships the app as non-root with an embedded `HEALTHCHECK`
- `docker-compose.yml` deployment: Ollama server (persistent weights) +
  one-shot model-pull bootstrap + triage API, fully env-overridable
- `docker-suite` CI workflow: tests inside the container on every push; runtime
  image published to GHCR on `main` (deploy = `docker pull`)
- `.dockerignore` keeping the build context lean and dependency-free

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
