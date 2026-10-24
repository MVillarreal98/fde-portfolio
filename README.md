# Automation portfolio · Miguel Villarreal

**Finance operations → automation · Python · SQL · LLMs · .NET**

[![portfolio-ci](https://github.com/MVillarreal98/fde-portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/MVillarreal98/fde-portfolio/actions/workflows/ci.yml)
[![docker-suite](https://github.com/MVillarreal98/fde-portfolio/actions/workflows/docker.yml/badge.svg)](https://github.com/MVillarreal98/fde-portfolio/actions/workflows/docker.yml)

Four self-contained projects built around problems that come up in billing and
payment operations: two money records that should agree and do not, free-text
customer claims that need a decision that follows policy, files that must
match a rigid layout down to the character, and a collections sheet where
every open invoice must age and escalate on schedule. A fifth project goes
outside that job: it maps, locality by locality, where in the Monterrey metro
people search iPhone over Samsung Galaxy and how that moved from 2020 to 2025,
crossing three public data sources.

> **Status, plainly.** These are portfolio demos. Every dataset is synthetic
> and was written for the demos, except [`iphone-vs-samsung`](projects/iphone-vs-samsung/),
> which is built on public data (Google Trends, the 2020 Census from INEGI,
> StatCounter) downloaded on the dates named in its README. No project has users
> or a production deployment, and nothing here measures business impact. The
> numbers below are test counts and measurements on synthetic data, except the
> iPhone vs Galaxy shares, which are read from those public sources; each
> project README gives the command, machine and versions behind them.

## Projects

| Project | Stack | What it does | Evidence in the repo |
|---|---|---|---|
| **[Reconciliation Engine](projects/reconciliation-engine/)** | Python · pandas · DuckDB SQL | Reconciles an operations ledger against a settlement file. Each reference gets exactly one status, 7 rules explain the differences, unusable rows go to `rejected_rows.csv`, and conservation checks stop the run if the totals do not add up. The same rules run in pandas and in SQL. | 171 pytest tests with 100% statement and branch coverage on pandas 2.3.3 and 3.1.0. Parity tests require identical findings from both engines. A full run on 1,000,000 synthetic rows per side took 12.7 s (pandas) or 11.1 s (SQL) in a single run on one desktop machine. |
| **[LLM Support Desk](projects/llm-support-desk/)** | Python (stdlib) · Ollama `llama3.2:1b` · SQLite · Docker | Triages payment claims. A local LLM proposes a category and severity; deterministic rules decide the action and can only escalate. Every decision is stored in SQLite with the prompt hash, the model and the rules that fired. | 133 pytest tests with 99% line and branch coverage, including prompt-injection tests against a fake model that obeys the injection. Offline eval on 23 labeled synthetic tickets: category agreement 13/23 for `llama3.2:1b` and 21/23 for the keyword fallback; 9 of the 10 tickets that must reach a human were escalated on the LLM path. |
| **[Document Layout Automator](projects/file-layout-automator/)** | C# · .NET 8 · WPF + console CLI | Turns CSV rows into fixed-width layout files. It rejects a value instead of truncating it, reports line, field and reason, and writes nothing while any row fails. The desktop app and the CLI share one runner. | 38 xunit tests, including golden tests that compare the committed `sample_output/` with the engine's output. `dotnet build -warnaserror` passes with 0 warnings. |
| **[Collections Aging SQL](projects/collections-aging-sql/)** | DuckDB SQL · thin Python harness | Ages every open invoice from the policy due date, assigns one escalating dunning stage, applies cash FIFO so surplus is unapplied and cannot read as money owed, and lists duplicate-payment candidate pairs. Unusable rows land in `rejected_rows.csv` with a reason, and the run stops if invoiced ≠ applied + outstanding. | 37 pytest tests, including golden tests that diff all seven committed output files against a fresh run (LF everywhere: the report matches on Windows too). Amount text that is not an integer literal is rejected, duplicated invoice or payment ids are rejected after their first occurrence, and conservation holds three identities: rows, invoice cents and every payment cent landing in exactly one bucket. Ruff, mypy and an 85% branch-coverage gate pass; the installed CLI reproduces `sample_output/` byte for byte. |
| **[iPhone vs Galaxy in Monterrey](projects/iphone-vs-samsung/)** | SQLite · Python (stdlib) · Leaflet map | Maps the search interest of iPhone vs Samsung Galaxy across the Monterrey metro (22 localities with data in 2020, 32 in 2025), matching Google Trends to the INEGI 2020 Census by locality name and setting the metro search share against StatCounter's national web-traffic share. | `build_db.py` rebuilds the base from the committed raw files and records each file in a `meta` table with its source, URL and capture date; the Trends→Census match precedence is covered by unit tests. `02_sanity_checks.sql` returns zero rows on the current build and CI runs the unit tests, the build, the sanity queries and the map generation. The README states the caveats: search interest, not users; national web traffic, not city-level usage. |
