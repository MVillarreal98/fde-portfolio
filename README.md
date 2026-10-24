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
> or
> a production deployment, and nothing here measures business impact. The
> numbers below are test counts and measurements on synthetic data; each project
> README gives the command, machine and versions behind them.

## Projects

| Project | Stack | What it does | Evidence in the repo |
|---|---|---|---|
| **[Reconciliation Engine](projects/reconciliation-engine/)** | Python · pandas · DuckDB SQL | Reconciles an operations ledger against a settlement file. Each reference gets exactly one status, 7 rules explain the differences, unusable rows go to `rejected_rows.csv`, and conservation checks stop the run if the totals do not add up. The same rules run in pandas and in SQL. | 171 pytest tests with 100% statement and branch coverage on pandas 2.3.3 and 3.1.0. Parity tests require identical findings from both engines. A full run on 1,000,000 synthetic rows per side took 12.7 s (pandas) or 11.1 s (SQL) in a single run on one desktop machine. |
| **[LLM Support Desk](projects/llm-support-desk/)** | Python (stdlib) · Ollama `llama3.2:1b` · SQLite · Docker | Triages payment claims. A local LLM proposes a category and severity; deterministic rules decide the action and can only escalate. Every decision is stored in SQLite with the prompt hash, the model and the rules that fired. | 133 pytest tests with 99% line and branch coverage, including prompt-injection tests against a fake model that obeys the injection. Offline eval on 23 labeled synthetic tickets: category agreement 13/23 for `llama3.2:1b` and 21/23 for the keyword fallback; 9 of the 10 tickets that must reach a human were escalated on the LLM path. |
| **[Document Layout Automator](projects/file-layout-automator/)** | C# · .NET 8 · WPF + console CLI | Turns CSV rows into fixed-width layout files. It rejects a value instead of truncating it, reports line, field and reason, and writes nothing while any row fails. The desktop app and the CLI share one runner. | 38 xunit tests, including golden tests that compare the committed `sample_output/` with the engine's output. `dotnet build -warnaserror` passes with 0 warnings. |
| **[Collections Aging SQL](projects/collections-aging-sql/)** | DuckDB SQL · thin Python harness | Ages every open invoice from the policy due date, assigns one escalating dunning stage, applies cash FIFO so surplus is unapplied and cannot read as money owed, and lists duplicate-payment candidate pairs. Unusable rows land in `rejected_rows.csv` with a reason, and the run stops if invoiced ≠ applied + outstanding. | 37 pytest tests, including golden tests that diff all seven committed output files against a fresh run (LF everywhere: the report matches on Windows too). Amount text that is not an integer literal is rejected, duplicated invoice or payment ids are rejected after their first occurrence, and conservation holds three identities: rows, invoice cents and every payment cent landing in exactly one bucket. Ruff, mypy and an 85% branch-coverage gate pass; the installed CLI reproduces `sample_output/` byte for byte. |

 reproduces `sample_output/` byte for byte. |
| **[iPhone vs Galaxy in Monterrey](projects/iphone-vs-samsung/)** | SQLite · Python (stdlib) · Leaflet map | Maps the search interest of iPhone vs Samsung Galaxy across 22–32 localities of the Monterrey metro for 2020 and 2025, fusing Google Trends with the INEGI Census by locality name match and comparing search share against real national usage (StatCounter). | The pipeline itself is verified: `build_db.py` rebuilds the base from the committed raw files (all hashed into a `meta` table), `02_sanity_checks.sql` returns zero rows on the current build, and CI runs the build, the sanity queries and the map generation on every push. README states caveats plainly: search interest, not users; national usage, not city-level. |

## Problem → root cause → solution → how it would be measured

### Reconciliation Engine

- **Problem.** An operations ledger (what was captured) and a processor's
  settlement file (what was paid out) should agree reference by reference.
  Double settlements, partial settlements, orphans and settled cancellations are
  easy to miss when the check is done by hand.
- **Root causes it is built around.** Lookups that do not aggregate per
  reference, IDs read as numbers (`00123` becomes `123`), amounts that fail to
  parse without warning (`1,250.00`), and one problem counted under two rules.
  The 16 edge cases found when reviewing v1.0.0 of this project are now
  regression tests: 15 run on both engines and one checks option validation.
- **Solution.** Every column is read as text and money as integer cents.
  Each side is aggregated per reference and joined one-to-one, and each
  reference gets one status by precedence. Seven rules explain the differences.
  Every row that cannot be used is written to `rejected_rows.csv` with a reason.
  Conservation checks stop the run with exit code 1, and `--fail-on-findings`
  returns exit code 2 for schedulers.
- **How it would be measured.** On real files, the measures would be: the share of
  references reconciled automatically, the share of findings that finance
  confirms, discrepancies found per period compared with the manual check, and
  the time from file arrival to a reviewed report. None of these has been
  measured, because there is no real data here.

### LLM Support Desk

- **Problem.** Payment claims arrive as free text. Refund and escalation
  decisions have to follow policy even when the model is wrong or manipulated.
- **Root cause it is built around.** Letting a model's answer drive a money
  decision directly. On the synthetic set, `llama3.2:1b` picks the right category
  13 times out of 23. In an earlier review run, a prompt injection turned a
  $4,800 fraud claim into "close ticket, no action".
- **Solution.** The ticket is sent to the model as data, and the answer must
  pass a JSON schema that keeps only whitelisted fields. Deterministic guardrails
  then set the final action: fraud wording, money above the first-line cap,
  low confidence and unauthorized charges all escalate, and no rule can lower an
  escalation. A keyword classifier takes over when Ollama is down. Decisions and
  metrics live in SQLite (`support-desk metrics`, `GET /api/metrics`).
- **How it would be measured.** On labeled real tickets, the measures would be:
  escalation recall, over-escalation, how often the rules override the model,
  agreement with the final human resolution, and time to first response. Today
  `support-desk eval` computes category agreement, escalation recall and
  over-escalation against labels, and the SQL metrics compute escalation and
  override rates from the decision log. Both run on synthetic data only. One
  miss is documented: TK-1016, a fraud described without fraud vocabulary and
  below the cap.

### Document Layout Automator

- **Problem.** Operators re-key or re-format files into rigid fixed-width
  layouts for downstream systems. One character too many shifts every field
  after it.
- **Root causes it is built around.** Padding without a length check (silent
  truncation or overflow), amounts with two valid spellings (`602` and
  `602.00`), non-ASCII characters silently written as `?`, and partial files
  that look complete.
- **Solution.** Layout profiles are declared in C#, and each accepted line is
  exactly the sum of the field widths. An oversized value rejects its row.
  Per-row errors are reported in Spanish with line, field and reason. The write
  is fail-closed and shared by the WPF app and a CLI (exit codes 0/1/2).
- **How it would be measured.** The measures would be: files blocked before
  upload, ingestion errors reported by the receiving system, and time per file
  compared with the manual process. None has been measured: both layout specs
  and all data are synthetic.

### Collections Aging SQL

- **Problem.** An open-invoice sheet has to say, per invoice, how much is still
  owed, how late it is, which reminder or final notice must go out, and
  whether that "double payment" is the same charge paid twice.
- **Root causes it is built around.** Amount keys parsed loosely (a text
  amount that is not an integer literal — pesos with decimals, exponent or
  underscore notation — used to be rounded into cents with no trace), cash applied out of order
  (surplus over the invoice total being read as money still owed), aging
  counted from the issue date instead of the due date, rejected rows
  disappearing between tools, duplicated invoice or payment ids (an export
  run twice inflating the money), and a duplicate rule that flags every pair in
  the book.
- **Solution.** Two CSVs go through one staging pass that reads everything as
  text, demands integer-literal amounts and casts with `TRY_CAST`; unusable
  rows land in `rejected_rows.csv` with the first problem that hit them, and
  a second, uniqueness, pass rejects repeated invoice and payment ids.
  Payments are applied FIFO in SQL (ties decided by file line order) and
  each applies only up to what the invoice owed; the surplus is unapplied cash
  in its own column. Buckets count days past the **due date** (current,
  1-30, 31-60, 61-90, 91-plus) and dunning stages only escalate
  (pre_dunning → D3 → D15 → D35 → D60). Duplicate candidates are pairs (same
  customer, same amount, ≤ 7 days) for a reviewer. Before any report is
  written, the runner checks three identities — invoice rows, invoice cents
  and every payment cent (applied + unapplied + orphan) — and stops with
  exit 1 if any fails; `--fail-on-findings` returns exit 2 for schedulers
  and a bad `--as-of` flag exits 4.
  The row identity holds by construction and is kept as a regression guard;
  the cents identity catches over-application. The project README lists what
  the staging does not catch yet.
- **How it would be measured.** On real files, the measures would be: the
  share of open invoices aged automatically, dunning letters sent on the
  correct day, duplicate candidates confirmed over dismissed, and time from
  file arrival to a distributed call sheet. None of these has been measured,
  because there is no real data here.

### iPhone vs Samsung Galaxy in Monterrey

- **Problem.** Locality-level claims about "where people prefer iPhone" are
  usually made with no sources: either anecdote or a screenshot of a hashtag.
  There is no public data of phone usage per city.
- **Root causes it is built around.** Trends gives locality names with no keys
  or coordinates (requiring a documented match to the Census so no locality is
  silently wrong), a theme search for "Samsung" would count TVs and
  microwaves (so the project uses topics, not keywords), and two separate
  Trends downloads are not comparable unless the share is read *within* each
  locality (that is what the schema forces).
- **Solution.** One SQLite base from three sources, each file recorded in
  `meta` with URL and date; SQL that reports the share per locality (weighting
  by Census population), the 2020→2025 change and the gap between Metro
  search (87% iPhone) and national usage (~39% Apple); sanity queries that
  turn every matching problem into named rows rather than silent loss; and an
  interactive satellite map. Python is stdlib-only: the base rebuilds without
  a single install.
- **How it would be measured.** On a real contract: the match rate
  Trends↔Census, coverage of metro population, and whether the interpolated
  map correlates with survey data. In the repo, the quality gates are the
  sanity checks returning zero rows and the CI job rebuilding it all clean.

## SQL in this repository

- **DuckDB** ([`projects/collections-aging-sql/src/aging_sql/sql/`](projects/collections-aging-sql/src/aging_sql/sql/)):
  `staging.sql` reads every column as text, casts with `TRY_CAST` and sends
  unusable rows to `rejected_rows.csv` through an ordered `CASE` (first
  problem wins). `t_applied` applies cash FIFO with a running
  `sum() OVER (PARTITION BY invoice_id ORDER BY paid_date, payment_id)` capped
  by what the invoice owed; `aging_buckets.sql` and `dunning_states.sql` read
  a `SET VARIABLE as_of` reference date, `duplicate_payment_candidates.sql`
  self-joins customer + amount + window, and `monthly_collections.sql` runs
  `LAG()` over an aggregated month per method. The runner checks the row and
  the cents identity before writing anything.
- **DuckDB** ([`reconciliation-engine/src/reconciliation/sql/`](projects/reconciliation-engine/src/reconciliation/sql/)):
  `matched.sql` aggregates each side with CTEs, spots repeated amounts with
  `count(*) OVER (PARTITION BY ...)`, joins with `FULL OUTER JOIN` and assigns
  the status with a `CASE`. There is one SQL file per rule, and
  `duplicate_charge_candidates.sql` solves a gaps-and-islands problem with
  `lag()` and a running `sum()` window. `tests/test_parity.py` requires the SQL
  engine and the pandas engine to return the same findings.
- **SQLite** ([`llm-support-desk/src/support_desk/store.py`](projects/llm-support-desk/src/support_desk/store.py)):
  the `decisions` table (the decision log) and `METRICS_SQL`: escalation,
  override and fallback rates, latency per source, and rules fired, counted with
  `json_each`.
- **SQLite** ([`projects/iphone-vs-samsung/sql/`](projects/iphone-vs-samsung/sql/)):
  base views carry the stable columns (`v_localidad` attaches coordinates,
  population and socioeconomic indicators to every Trends share;
  `v_localidad_cambio` reformats the two years into rows). On top of them:
  population-weighted shares with quartile ranks per year (Q1), each locality
  against the metro average in its own year, dispersion (Q5), the 2020→2025
  change, and pure-SQL Pearson correlations (Q4) between the iPhone share and
  three census indicators — no pandas in the analysis path.
  `05_contexto_nacional.sql` left-joins the metro search share with
  StatCounter usage per year and reports the gap in pp.

## Repository-wide checks

- **CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on
  pushes to `main`, `feat/**` and `fix/**`, and on pull requests to `main`:
  - reconciliation-engine, on pandas 2.x and 3.x: `pip install -e ".[dev]"`,
    ruff, mypy, pytest with an 85% coverage gate, and two smoke checks. The
    installed `reconcile` command must reproduce `sample_output/`, and the SQL
    engine must exit with code 2 when there are findings.
  - llm-support-desk: ruff, mypy and pytest with a 95% coverage gate.
  - collections-aging-sql: ruff, mypy and pytest with an 85% branch-coverage
    gate, and two smoke checks. The installed `collections-aging` command must
    reproduce `sample_output/`, and under `--fail-on-findings` it must exit
    with code 2 while findings exist.
  - iphone-vs-samsung (stdlib-only, no install step): the pipeline
    itself is the smoke check — `build_db.py`, an empty result from
    `02_sanity_checks.sql`, and a generated `insights/mapa_mty.html`.
  - file-layout-automator, on Windows: `dotnet build -warnaserror`,
    `dotnet test`, and a CLI smoke check (exit 0 on clean input; exit 1 and no
    file written on the planted bad rows).
- **Docker** ([`.github/workflows/docker.yml`](.github/workflows/docker.yml))
  builds the support desk's `test` stage, so the suite runs inside the image.
  It then starts the runtime image without Ollama and waits for its healthcheck
  to report `healthy`. On `main` it publishes the runtime image to GHCR.
- **Pre-commit** ([`.pre-commit-config.yaml`](.pre-commit-config.yaml)) runs
  ruff lint and format plus basic file hygiene.

## Background (context, not impact of these tools)

Before this portfolio I worked as a Billing Specialist at Central Transport
(Monterrey, Nov 2023 – Jul 2025). I processed 240+ bills of lading a day and
1,000+ invoices a month, with billing accuracy of 99%+ (figures from my CV).
That work is why these problems were chosen. These projects were built after
that role and were never used there, and no data, code or figure from it
appears in this repository.

The synthetic data uses Mexican retail payment rails as its setting: OXXO cash
payments, SPEI transfers and cards. The projects are not affiliated with any
company.

## How it was built

Built with the help of AI coding tools. Each project's README documents its
design decisions, how it is tested and its known limitations, and each
CHANGELOG records what changed between versions.

## Quick review

Tested on Python 3.12 (the only Python version CI runs) and the .NET 8 SDK
on Windows. Run each block from the repository root; the subshells keep the
`cd` local to its project.

```bash
# Reconciliation Engine
(cd projects/reconciliation-engine && pip install -e ".[dev]" && pytest && python run_reconciliation.py)

# LLM Support Desk (stdlib runtime; Ollama is optional, the keyword fallback runs without it)
(cd projects/llm-support-desk && pip install -e ".[dev]" && python -m pytest -q -p no:cacheprovider && support-desk eval --mode fallback)

# LLM Support Desk — one-command full deployment (start Ollama, pull the model, run the desk)
(cd projects/llm-support-desk && docker compose up --build)   # UI at http://localhost:8000

# Document Layout Automator (Windows)
(cd projects/file-layout-automator && dotnet build DocumentLayoutAutomator.sln && dotnet test tests)

# Collections Aging SQL
(cd projects/collections-aging-sql && pip install -e ".[dev]" && pytest && python run_collections_aging.py)

# iPhone vs Galaxy in Monterrey (stdlib-only; sqlite3 CLI needed for the sanity pass)
(cd projects/iphone-vs-samsung && python scripts/build_db.py && sqlite3 db/iphone_vs_samsung.sqlite < sql/02_sanity_checks.sql && python scripts/mapa_mty.py)
```

You can review each project without building it. The reconciliation,
collections-aging and layout projects commit their real demo output under
`sample_output/`; iphone-vs-samsung commits the generated map, and its base
rebuilds from the committed raw files. The reconciliation, support-desk and
layout projects commit screenshots taken from the current code.

## Layout

```
projects/reconciliation-engine/   Python · pandas · DuckDB SQL
projects/llm-support-desk/        Python · Ollama · SQLite · Docker
projects/file-layout-automator/   C# · .NET 8 · WPF + CLI
projects/collections-aging-sql/   DuckDB SQL · thin Python harness
projects/iphone-vs-samsung/       SQLite · Python (stdlib) · Leaflet map
docs/executive-summary.md         one-page summary (docs/build_summary.py generates the .txt and .html; the .pdf is printed from the .html)
.github/workflows/                CI and Docker workflows
```

MIT licensed (see [LICENSE](LICENSE)).
