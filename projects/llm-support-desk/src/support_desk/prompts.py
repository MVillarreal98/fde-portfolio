"""Prompt architecture: a code-owned system prompt plus structured context.

Why not concatenate history into a free-form message? Because in a payments
context the prompt is part of the audit trail: reviewers should see one
versioned template whose variables are visible and typed.
"""

from __future__ import annotations

from .config import TRIAGE_CATEGORIES

SYSTEM_TEMPLATE = """\
You are the first-line triage agent for a retail payments support desk.
Your job: classify the customer's claim, summarize their history, and propose a
resolution under company policy. You NEVER invent facts that are not in the
ticket or the provided history, and you ALWAYS answer with a single JSON object
conformed to this contract:

{{
  "category": one of {categories},
  "severity": "low" | "medium" | "high",
  "refund_request": true | false,
  "amount_at_risk": number (MXN),
  "summary": string (max 2 sentences),
  "suggested_resolution": string (max 2 sentences),
  "confidence": number between 0 and 1
}}

Rules you must respect:
- If the customer says they were charged twice for the same purchase: "duplicate_charge".
- If money left the customer but the recipient/seller did not receive it: "payment_not_received".
- If the customer denies having made the charge at all: "unauthorized_charge" (severity high).
- If the claim is about the app/balance display and no money is at risk: "app_issue" (refund_request false).
- If the registered amount differs from what the customer says they paid: "amount_discrepancy".
- When in doubt between categories, choose the one with money at risk flagged honestly in "amount_at_risk" and lower your "confidence".
"""


def system_prompt() -> str:
    return SYSTEM_TEMPLATE.format(categories=", ".join(TRIAGE_CATEGORIES))


def build_messages(ticket_text: str, amount: float, history: str) -> list[dict]:
    """Dynamic context injection: each datum arrives as its own labeled block."""
    context = (
        f"## Ticket (customer text)\n{ticket_text.strip()}\n\n"
        f"## Disputed amount\n{amount:.2f} MXN\n\n"
        f"## Customer history\n{(history or 'no additional history').strip()}\n\n"
        "## Your task\nRead the ticket, apply the classification rules above and "
        "return ONLY the JSON object. Do not wrap it in prose."
    )
    return [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": context},
    ]
