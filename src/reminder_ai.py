"""
DECISION LOGIC step of the automation journey.

This module is where an AI model will be called to judge how risky an
overdue invoice is, and draft a follow-up reminder message with a tone that
matches that risk. The decision depends on:
  - how many days the invoice is overdue
  - how many times this customer has paid late before (past_late_count)

For this first version, generate_reminder_draft() uses a RULE-BASED
placeholder (no AI call yet) so the rest of the app can be built and tested
end-to-end first. We will swap the body of this function to call a real
LLM API next, WITHOUT changing any other file or any other function's
signature — that is the point of isolating this logic in its own module.
"""


def _assess_risk(days_overdue: int, past_late_count: int) -> str:
    """Decide the risk tier for this overdue invoice: low / medium / high.

    This is the 'AI makes a judgment call' part of ChaseFlow (not just
    drafting text) — it looks at the pattern of this customer's behaviour,
    not just the amount owed, and recommends how urgently to act.
    This rule will stay even after we add the AI call: it is the business
    logic deciding which risk tier applies, which is different from the AI
    writing the actual sentence."""
    if days_overdue <= 5 and past_late_count == 0:
        return "low"
    if days_overdue <= 14 or past_late_count <= 1:
        return "medium"
    return "high"


_TONE_FOR_RISK = {
    "low": "gentle",
    "medium": "firm",
    "high": "final_notice",
}

_ACTION_FOR_RISK = {
    "low": "Gentle nudge — this customer usually pays within the week once reminded.",
    "medium": "Firm follow-up — flag for a second check if still unpaid next review.",
    "high": "Final notice — consider a phone call if there's no reply within 48 hours.",
}


def assess_invoice_risk(invoice: dict) -> dict:
    """Lightweight risk assessment only (no message draft).

    Used on the overdue-invoices list page, so we can show every row's risk
    tier and recommended action WITHOUT calling the (future) AI API once per
    row just to render a list. The full draft (generate_reminder_draft) is
    only generated when the owner opens one specific invoice to act on it.
    """
    days = invoice.get("days_overdue", 0)
    past_late_count = invoice["past_late_count"]
    risk_tier = _assess_risk(days, past_late_count)
    return {
        "risk_tier": risk_tier,
        "recommended_action": _ACTION_FOR_RISK[risk_tier],
    }


def generate_reminder_draft(invoice: dict) -> dict:
    """
    Returns a dict describing ChaseFlow's recommendation for one overdue
    invoice, for a human to review/edit/approve before anything is sent:

      {
        "risk_tier": "low" | "medium" | "high",
        "tone": "gentle" | "firm" | "final_notice",
        "recommended_action": str,   # plain-English advice for the owner
        "message": str,              # the editable draft reminder text
      }

    TODO (next step): replace the message-building below with a real AI API
    call that takes (customer_name, amount, days_overdue, past_late_count,
    tone) and generates natural, personalised wording. The risk/tone
    decision above stays the same either way — the AI drafts the sentence,
    the rule above decides how firm that sentence should be.
    """
    days = invoice.get("days_overdue", 0)
    past_late_count = invoice["past_late_count"]
    name = invoice["customer_name"]
    amount = invoice["amount"]

    risk_tier = _assess_risk(days, past_late_count)
    tone = _TONE_FOR_RISK[risk_tier]
    recommended_action = _ACTION_FOR_RISK[risk_tier]

    if tone == "gentle":
        message = (
            f"Hi {name}, just a friendly reminder that invoice for RM{amount:.2f} "
            f"was due {days} day(s) ago. Could you let us know when we can expect "
            f"payment? Thank you!"
        )
    elif tone == "firm":
        message = (
            f"Dear {name}, this is a follow-up on your outstanding invoice of "
            f"RM{amount:.2f}, now {days} days overdue. Please arrange payment "
            f"as soon as possible, or contact us if there is an issue we should know about."
        )
    else:  # final_notice
        message = (
            f"Dear {name}, your invoice of RM{amount:.2f} is significantly overdue "
            f"({days} days) and this is a repeated late payment on your account. "
            f"Please settle this immediately to avoid a pause on future orders. "
            f"Contact us today to resolve this."
        )

    return {
        "risk_tier": risk_tier,
        "tone": tone,
        "recommended_action": recommended_action,
        "message": message,
    }