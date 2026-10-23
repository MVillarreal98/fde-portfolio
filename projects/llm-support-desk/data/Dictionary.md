# Data Dictionary — sample tickets

`data/sample_tickets.csv` is **synthetic**: claims written to exercise every
triage category deterministically (verified by the fallback classifier and the
business rules). It contains no personal data.

| Column | Type | Meaning |
|---|---|---|
| `ticket_id` | string | Ops-facing ticket identifier (`TK-1001`–`TK-1005`). |
| `channel` | enum | Rail the claim is about: `OXXO`, `SPEI`, `CARD`, `APP`. |
| `customer_text` | string | Free-text claim as the customer submitted it (the LLM input). |
| `amount` | decimal(2) | Amount the customer claims is at stake, MXN (0.00 = no money at risk). |
| `history` | string | Summarized customer history injected as context to the model. |

## Expected triage outcome (per claim)
| Ticket | Expected category | Severity | Refund? | Notes |
|---|---|---|---|---|
| TK-1001 | `duplicate_charge` | medium | yes | Verified twice paid by the terminal. |
| TK-1002 | `payment_not_received` | medium | yes | Above the $500 first-line refund cap: rules escalate the refund to supervisor. |
| TK-1003 | `unauthorized_charge` | high | yes | Rules force high severity; >cap → supervisor. |
| TK-1004 | `app_issue` | low | no | Zero amount: no first-line refund. |
| TK-1005 | `amount_discrepancy` | medium | yes | $180 difference vs $130 recorded. |
