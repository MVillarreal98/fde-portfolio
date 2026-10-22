# Executive Summary — Forward Deployed Engineer Portfolio

**Candidate focus:** Forward Deployed Engineer, Spin (OXXO / fintech payments)

## Thesis

A Forward Deployed Engineer succeeds by turning an operational pain point into a working tool with a measurable payoff. Every project in this portfolio follows the same arc:

> *Here was the daily problem → Here is the tool I built → Here is what it saved.*

## Results

| Project | Business Problem | Solution Delivered | Impact |
|---|---|---|---|
| Reconciliation Engine | Daily reconciliation between operational records and billing/settlement data was manual (+240 invoices/day audited) and missed systemic anomalies. | Modular Python pipeline: ingestion, cleaning, cross-matching on IDs and amounts, anomaly detection (duplicates, mismatches, orphans), automated executive report export. | Replaced hours of manual cross-checking with a repeatable 5-minute run; anomalies surface daily instead of at month-end. |
| LLM Support Desk | Support teams triage high volumes of unstructured user claims without consistency or audit trails. | Python web application integrating a local LLM (Ollama REST): dynamic context injection, controlled system prompt, JSON-structured responses, and deterministic business rules on top of model output. | Production-shaped architecture for an agent that classifies claims, summarizes transaction histories, and proposes resolutions — runnable fully on-premise, so no sensitive payment data leaves the network. |
| File Layout Automator | Repeated manual re-formatting of files for downstream systems was slow and error-prone for non-technical staff. | Windows desktop application (C#/.NET WPF): friendly GUI, deterministic transformation rules encoded once, validation and clear error feedback. | Eliminated hand-edited files; end users completed in minutes what previously required careful manual work, with a zero-training interface. |

## Skills demonstrated

- **Data & reconciliation:** pandas pipelines, fuzzy/exact matching, anomaly heuristics, executive reporting, SQL.
- **AI engineering:** local LLM integration, prompt & context architecture, structured (JSON) output contracts, rules layer above probabilistic outputs.
- **Product delivery end to end:** requirements discovery → MVP scope → desktop/GUI delivery to non-technical operators.
- **Engineering practice:** modular code, tests, Git feature-branch workflow, reproducible documentation.
