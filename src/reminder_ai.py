"""
DECISION LOGIC step of the automation journey.

For one overdue invoice, this module asks an AI model (Google Gemini) to:
  1. judge the risk tier (low / medium / high)
  2. recommend what the SME owner should do next
  3. draft a reminder message in a tone that matches that risk, written in the
     language the customer does business in (English / Bahasa Malaysia / Chinese)

A human always reviews and approves the result before anything is sent.

Two layers, on purpose:
  - RULES (_assess_risk): a simple, transparent baseline from days overdue and
    past late payments. It is given to the AI as a starting point, and it is
    the fallback if the AI is unavailable, so the app never breaks in a demo.
  - AI (_ask_gemini): reads the full context, confirms or adjusts the baseline,
    explains why, and writes the actual message.
"""

import json
import os

import requests

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VALID_TIERS = ("low", "medium", "high")

# Languages a Malaysian SME commonly uses with its customers.
#   label  -> shown on the language switch
#   prompt -> how we describe it to the AI
#   signoff-> how the message ends
LANGUAGES = {
    "en": {
        "label": "English",
        "prompt": "English",
        "signoff": "Accounts Team",
    },
    "ms": {
        "label": "Bahasa Malaysia",
        "prompt": "Bahasa Malaysia, polite but natural, as used in Malaysian business WhatsApp chats",
        "signoff": "Pasukan Akaun",
    },
    "zh": {
        "label": "中文",
        "prompt": "Simplified Chinese, polite and natural, as used in Malaysian business WhatsApp chats",
        "signoff": "财务部",
    },
}
DEFAULT_LANGUAGE = "en"


def normalise_language(code) -> str:
    """Any unknown/missing language code falls back to English."""
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


# --------------------------------------------------------------------------
# Layer 1: transparent rules (baseline + fallback)
# --------------------------------------------------------------------------

def _assess_risk(days_overdue: int, past_late_count: int) -> str:
    """Baseline risk tier from two simple facts about the invoice."""
    if days_overdue <= 5 and past_late_count == 0:
        return "low"
    if days_overdue <= 14 or past_late_count <= 1:
        return "medium"
    return "high"


_TONE_FOR_RISK = {"low": "gentle", "medium": "firm", "high": "final_notice"}

_ACTION_FOR_RISK = {
    "low": "Gentle nudge — this customer usually pays within the week once reminded.",
    "medium": "Firm follow-up — flag for a second check if still unpaid next review.",
    "high": "Final notice — consider a phone call if there's no reply within 48 hours.",
}


_RULE_TEXT = {
    "low": "Rule: Low = overdue 5 days or fewer AND no earlier late payments.",
    "medium": "Rule: Medium = not Low, and overdue 14 days or fewer OR at most 1 earlier late payment.",
    "high": "Rule: High = overdue more than 14 days AND at least 2 earlier late payments.",
}


def explain_risk(days_overdue: int, past_late_count: int) -> dict:
    """The deterministic part of the risk judgement, spelled out.

    Returns the tier plus the plain facts behind it and the exact rule that
    produced it. No AI and no invented numbers: this is the same rule as
    _assess_risk, just explained, so the owner can check it by hand."""
    tier = _assess_risk(days_overdue, past_late_count)

    if days_overdue <= 5:
        days_text = f"{days_overdue} day(s) overdue (5 or fewer)"
    elif days_overdue <= 14:
        days_text = f"{days_overdue} days overdue (6 to 14)"
    else:
        days_text = f"{days_overdue} days overdue (more than 14)"

    if past_late_count == 0:
        late_text = "No earlier late payments on record"
    elif past_late_count == 1:
        late_text = "1 earlier late payment on record"
    else:
        late_text = f"{past_late_count} earlier late payments on record"

    return {"risk_tier": tier, "factors": [days_text, late_text], "rule": _RULE_TEXT[tier]}


def assess_invoice_risk(invoice: dict) -> dict:
    """Quick rule-based risk for the overdue LIST page.

    No AI call here: we don't want one API request per table row just to
    show a list. The AI looks at an invoice only when the owner opens it.
    """
    explained = explain_risk(invoice.get("days_overdue", 0), invoice["past_late_count"])
    return {
        "risk_tier": explained["risk_tier"],
        "recommended_action": _ACTION_FOR_RISK[explained["risk_tier"]],
        "factors": explained["factors"],
        "rule": explained["rule"],
    }


def _rule_based_message(invoice: dict, tone: str, language: str) -> str:
    """Fixed templates, 3 tones x 3 languages. Used only if the AI is unavailable."""
    name = invoice["customer_name"]
    no = invoice.get("invoice_no", "your invoice")
    amount = f"RM{invoice['amount']:.2f}"
    days = invoice.get("days_overdue", 0)

    if language == "ms":
        if tone == "gentle":
            return (
                f"Hai {name}, ini peringatan mesra bahawa invois {no} ({amount}) telah "
                f"tamat tempoh {days} hari yang lalu. Bolehkah anda maklumkan bila "
                f"pembayaran boleh dibuat? Terima kasih! — Pasukan Akaun"
            )
        if tone == "firm":
            return (
                f"Salam {name}, ini susulan mengenai invois {no} ({amount}) yang telah "
                f"tertunggak {days} hari. Sila jelaskan pembayaran secepat mungkin, atau "
                f"hubungi kami jika terdapat sebarang masalah. — Pasukan Akaun"
            )
        return (
            f"Salam {name}, invois {no} ({amount}) telah tertunggak terlalu lama "
            f"({days} hari) dan ini bukan kali pertama pembayaran dilewatkan. Sila "
            f"jelaskan dengan segera bagi mengelakkan tempahan akan datang dijeda. "
            f"Hubungi kami hari ini untuk menyelesaikannya. — Pasukan Akaun"
        )

    if language == "zh":
        if tone == "gentle":
            return (
                f"{name} 您好，温馨提醒：发票 {no}（{amount}）已逾期 {days} 天。"
                f"请问何时可以安排付款？谢谢！— 财务部"
            )
        if tone == "firm":
            return (
                f"{name} 您好，关于发票 {no}（{amount}），现已逾期 {days} 天。"
                f"请尽快安排付款；如有任何问题，也请及时与我们联系。— 财务部"
            )
        return (
            f"{name} 您好，发票 {no}（{amount}）已严重逾期（{days} 天），"
            f"且这已不是第一次延迟付款。请立即结清，以免影响后续订单。"
            f"请今天与我们联系处理。— 财务部"
        )

    # English (default)
    if tone == "gentle":
        return (
            f"Hi {name}, just a friendly reminder that invoice {no} ({amount}) "
            f"was due {days} day(s) ago. Could you let us know when we can expect "
            f"payment? Thank you! — Accounts Team"
        )
    if tone == "firm":
        return (
            f"Dear {name}, this is a follow-up on invoice {no} ({amount}), now "
            f"{days} days overdue. Please arrange payment as soon as possible, or "
            f"contact us if there is an issue we should know about. — Accounts Team"
        )
    return (
        f"Dear {name}, invoice {no} ({amount}) is significantly overdue "
        f"({days} days) and this is a repeated late payment on your account. "
        f"Please settle this immediately to avoid a pause on future orders. "
        f"Contact us today to resolve this. — Accounts Team"
    )


def _rule_based_draft(invoice: dict, language: str) -> dict:
    days = invoice.get("days_overdue", 0)
    risk_tier = _assess_risk(days, invoice["past_late_count"])
    tone = _TONE_FOR_RISK[risk_tier]
    return {
        "risk_tier": risk_tier,
        "tone": tone,
        "recommended_action": _ACTION_FOR_RISK[risk_tier],
        "reasoning": "Rule-based fallback: based on days overdue and past late payments.",
        "message": _rule_based_message(invoice, tone, language),
        "language": language,
        "source": "rules",
    }


# --------------------------------------------------------------------------
# Layer 2: the AI call
# --------------------------------------------------------------------------

def _build_prompt(invoice: dict, baseline_tier: str, language: str) -> str:
    lang = LANGUAGES[language]
    return f"""You are a collections assistant for a small business in Malaysia.
An invoice is overdue. Decide how risky it is and help the owner follow up.

Invoice facts:
- Customer: {invoice["customer_name"]}
- Invoice number: {invoice.get("invoice_no", "n/a")}
- Amount: RM{invoice["amount"]:.2f}
- Days overdue: {invoice.get("days_overdue", 0)}
- Times this customer has paid late before: {invoice["past_late_count"]}

A simple rule suggests the risk tier "{baseline_tier}". You may keep it or move it
by one level if the facts justify it (for example a large amount, or a worsening pattern).

Return ONLY a JSON object with exactly these keys:
- "risk_tier": one of "low", "medium", "high"
- "recommended_action": one sentence of practical advice for the business owner, in English
- "reasoning": one or two sentences explaining why you chose this tier, in English
- "message": a reminder message to send to the customer on WhatsApp, 2 to 4 short
  sentences, written in {lang["prompt"]}. Mention the invoice number and the amount.
  Tone: low = friendly and gentle, medium = polite but firm, high = serious final notice.
  Use only the facts above. Do not invent dates, bank details or penalties.
  Sign off as "{lang["signoff"]}"."""


def _ask_gemini(invoice: dict, baseline_tier: str, language: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    response = requests.post(
        GEMINI_URL.format(model=GEMINI_MODEL),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": _build_prompt(invoice, baseline_tier, language)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.4,
            },
        },
        timeout=25,
    )
    response.raise_for_status()

    parts = response.json()["candidates"][0]["content"]["parts"]
    result = json.loads("".join(p.get("text", "") for p in parts))

    # Don't blindly trust the model's output: check it before using it.
    tier = str(result.get("risk_tier", "")).lower()
    if tier not in VALID_TIERS:
        raise ValueError(f"AI returned invalid risk_tier: {tier!r}")
    for key in ("recommended_action", "reasoning", "message"):
        if not str(result.get(key, "")).strip():
            raise ValueError(f"AI response missing '{key}'")

    return {
        "risk_tier": tier,
        "tone": _TONE_FOR_RISK[tier],
        "recommended_action": result["recommended_action"].strip(),
        "reasoning": result["reasoning"].strip(),
        "message": result["message"].strip(),
        "language": language,
        "source": "ai",
    }


def generate_reminder_draft(invoice: dict, language: str = DEFAULT_LANGUAGE) -> dict:
    """Returns the recommendation for one overdue invoice, for a human to
    review, edit and approve:

      {
        "risk_tier": "low" | "medium" | "high",
        "tone": "gentle" | "firm" | "final_notice",
        "recommended_action": str,
        "reasoning": str,     # why this tier
        "message": str,       # editable draft, in the chosen language
        "language": "en" | "ms" | "zh",
        "source": "ai" | "rules",   # who produced it
      }

    If the AI call fails for any reason (no key, network, bad output), we fall
    back to the rule-based draft so the owner is never left with nothing.
    """
    language = normalise_language(language)
    baseline_tier = _assess_risk(invoice.get("days_overdue", 0), invoice["past_late_count"])
    try:
        return _ask_gemini(invoice, baseline_tier, language)
    except Exception as error:  # noqa: BLE001 - deliberate catch-all, see docstring
        print(f"[reminder_ai] AI call failed, using rule-based fallback: {error}", flush=True)
        return _rule_based_draft(invoice, language)