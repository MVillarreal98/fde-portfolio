# Changelog

All notable changes to the LLM Support Desk are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-10-23
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
