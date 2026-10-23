# Forward Deployed Engineer Portfolio

[![portfolio-ci](https://github.com/YOUR-USER/YOUR-REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR-USER/YOUR-REPO/actions/workflows/ci.yml)
<!-- Substitute YOUR-USER/YOUR-REPO after publishing to GitHub -->

**Business problem → custom tool → measurable impact.** Three real projects, each built around the way fintech operations actually work at scale (high-volume retail payment rails like OXXO, SPEI, and card settlements).

> Built for Forward Deployed Engineer roles: every project below starts from a real operational pain I lived (auditing +240 invoices/day, building reporting pipelines for logistics), then shows the tool I built to fix it and the hours or dollars it saved.

📄 Plain-text executive summary for email/ATS attachments: [docs/executive-summary.txt](docs/executive-summary.txt)

---

## The Portfolio at a Glance

| # | Project | Stack | The Business Problem | The Impact |
|---|---------|-------|----------------------|------------|
| 1 | **[Reconciliation Engine](projects/reconciliation-engine/)** | Python · Pandas · SQL | Daily financial reconciliation across two data sources (ops ledger vs. billing/settlement) was manual, error-prone, and did not catch anomalies systematically. | Flagged duplicate charges, amount mismatches, and orphaned transactions automatically; turned a daily manual audit into a 5-minute automated report. |
| 2 | **[LLM Support Desk](projects/llm-support-desk/)** | Python · Ollama REST · Web UI | Support and operations teams drown in unstructured tickets. LLM flows must control context, enforce structured output, and follow business rules to be useful in production. | AI-powered triage agent: classifies claims, summarizes transaction history, and suggests resolutions under deterministic business rules — deployable locally (no data leaves the premises). |
| 3 | **[Document Layout Automator](projects/file-layout-automator/)** | C# · .NET (WPF) | Users ran a repetitive, error-prone manual process of re-laying-out files for downstream systems, with zero tolerance for formatting mistakes. | GPU-free desktop MVP with a friendly GUI enforcing deterministic transformation rules — discovered the pain, shipped a working product end to end. |

---

## Why this portfolio matches a Forward Deployed Engineer role

1. **Deployment is the point.** Each project was designed with the end user (operations analyst, support agent, clerical staff) first, not the codebase.
2. **Full discovery→delivery arc.** I identified the pain, scoped the minimum viable tool, built it, and handed it to non-technical users.
3. **Fintech-relevant skills.** High-volume transaction processing, reconciliation, anomaly detection, structured LLM flows, and rules-based automation are the daily bread of payment platforms like Spin + OXXO.

## Development workflow

Each project lives on its own feature branch and is merged into `main` as a self-contained folder once complete:

```
main
├── feat/reconciliation-detection   → projects/reconciliation-engine/
├── feat/llm-webapp                 → projects/llm-support-desk/
└── feat/desktop-automation         → projects/file-layout-automator/
```

The shared documentation (`README`, [executive summary](docs/executive-summary.md)) is maintained on `main`.
