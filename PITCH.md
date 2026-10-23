# Interview Pitch Guide

One page per project: the 40-second narrative, the hard questions you should
expect, and the exact answer. Practice out loud, ≤90 seconds each.

---

## 1) Reconciliation Engine — "I defend money with deterministic rules"

### The 40-second pitch
> "In operations I audited **+240 invoices daily** and reconciliation was
> filter-by-filter in spreadsheets — hours per day and still prone to miss
> systemic issues. I built a modular Pandas pipeline that reconciles the
> operational ledger against billing/settlement exports and applies four
> deterministic anomaly rules: duplicate settlements, amount mismatches beyond
> cent tolerance, one-sided orphans in either direction, and duplicate
> same-day captures. The engine flagged all planted anomalies in the demo
> automatically, and every rule is a pure, unit-tested function — one
> green CI suite proves the exact same rules that support the demo. The output
> is an executive report plus per-rule CSVs finance can act on line by line."

### Expected hard questions & answers
| Question | Your answer |
|---|---|
| "Why not fuzzy matching?" | "First exact matching on the transaction reference with aggregation per reference; the four rules are pure functions. Fuzzy only if the business justifies tolerance for capture errors — I'd validate precision/recall on historical discrepancies first." |
| "How does it scale to millions of rows?" | "Same design on DuckDB/Polars or the warehouse engine; the matching model (keyed aggregation + tolerance rules) does not change — that separation is the point of the architecture." |
| "What if a settlement groups many transactions?" | "Aggregation is per reference: settlement file grouping is composed from the same primitives; ops pairs match via sum of parts when IDs are carried and flagged when they are not." |
| "Show real impact." | "On the demo: 24 transactions reconciled, 4 rules fired, net flagged difference **$2,363 MXN** — including a double-settle of $3,400 that a manual pass would have paid out." |

---

## 2) LLM Support Desk — "The model proposes; deterministic rules dispose"

### The 40-second pitch
> "This is the architecture I would deploy as a claim-triage agent for a
> payments desk. A local LLM (Ollama, on-premise — no transaction data leaves
> the network) classifies the claim under a code-owned system prompt with
> typed context injection. The model is forced into JSON at the protocol
> level, and the response is validated by a fail-closed schema. Crucially, a
> deterministic rules layer sits **above** the model: refund autocap,
> low-confidence escalation to a human, forced severity on unauthorized
> charges. If inference is down, an auditable keyword classifier keeps the
> desk running and the UI shows the decision's source (llm/fallback) — the
> audit trail never lies."

### Expected hard questions & answers
| Question | Your answer |
|---|---|
| "Why Ollama and not OpenAI/Anthropic?" | "Privacy first for payment data; the client is isolated so swapping providers is one module. On-premise also removes latency/availability risk for a live support desk." |
| "How do you prevent hallucinations?" | "I don't pretend to prevent them — I capture them. JSON contract with schema validation that fails closed, whitelist categories, and confidence-gated execution: below the threshold nothing auto-executes, the claim escalates with context prepared." |
| "How would you measure quality?" | "Weekly agreement rate between agent suggestions and final human resolution on a labeled sample; the UI already persists the source and decision for that audit." |
| "What's the hardest bug you hit?" | "Give a real one: the fallback classifier missed 'I paid twice' because the keyword set covered 'charged twice' but not variants — I extended the lexicon and added the exact regression case; the same honesty pattern (schema rejects unknown categories) caught model output drift in tests." |

---

## 3) Document Layout Automator — "Discovery to shipped MVP end to end"

### The 40-second pitch
> "End-user operators had to re-layout transactions files by hand for
> downstream ERP and carrier systems — repetitive, zero tolerance for error.
> I scoped the smallest tool that removes the practice: a Windows desktop app,
> one screen, friendly for non-technical users. The transformation logic is a
> declarative rule engine — per column: source field, fixed width, padding,
> regex validation, default when empty — so profiles are auditable code, not
> loose settings. Every rejected row is reported with its line number and a
> plain-language reason, and the run is fail-closed: no output artifact is
> written while any row fails. Same input, same output, guaranteed by five
> xunit tests that pin the exact fixed-width lines."

### Expected hard questions & answers
| Question | Your answer |
|---|---|
| "Why a desktop app and not a script or web service?" | "The user's environment was fixed: no package installs, no training budget. The best deployment is the one the operator actually adopts — that's the Forward Deployed Engineer thesis; the engine still runs headless for CI." |
| "How do you avoid breaking the partner feed?" | "Fail-closed run semantics: rejections block the artifact; determinism is pinned by byte-exact expected-string tests." |
| "What would you change at scale?" | "Profile files would move to config driven by pipeline owners, and I'd add a dry-run diff mode before overwriting the previous day's artifact." |

---

## Cross-cutting closer (30 seconds)
> "Everything is one Git repo with a **branch per project**, conventional
> commits, three green CI suites (12 tests), zero compiler warnings, and every
> demo artifact committed under `sample_output/` so a reviewer can verify
> without building anything. Same discipline I'd bring to a Forward Deployed
> engagement: deploy the tool the business needs, leave maintainable code and
> a measurable improvement behind."
