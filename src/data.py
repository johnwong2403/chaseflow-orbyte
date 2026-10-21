"""
In-memory data layer for the ChaseFlow MVP.

Why in-memory instead of a real database for the prototype:
- Our deadline is a few days away; a real DB (Postgres/SQLite file) adds setup
  risk for no judging benefit at this stage.
- All data here is SYNTHETIC (made up), per competition rules — no real SME
  or customer data is used anywhere in this project. Phone numbers are fake.

If this were a production Orbyte module, this file is exactly where a real
database (e.g. SQLite/Postgres via SQLAlchemy) would replace the Python lists.
In Orbyte terms: customers (name, phone, preferred language) would come from
the People module, and invoices + payments from the Connect module.

Single source of truth
----------------------
  CUSTOMERS  holds each customer once (name, phone, preferred language).
  INVOICES   refers to a customer by customer_id, and holds the money facts
             (amount, due date, status, paid date).
  The customer's "late payments on record" is NOT typed in by hand: it is
  counted from that customer's paid invoices (paid after the due date), so it
  always agrees with the payment records shown on the Customer page.
  The convenience fields on each invoice (customer_name, phone,
  preferred_language, past_late_count) are filled in from those two sources
  by _sync_customer_fields(); never edit them directly.

Invoice status lifecycle:
    Unpaid  --(owner approves a reminder)-->  Reminded  --(payment received)-->  Paid

Payment promises
----------------
  When a customer says "I will pay on <date>", the owner records it as a
  promise on that invoice (PROMISES). A promise's status (pending / kept /
  paid late / broken / replaced) is never typed in: it is worked out from the
  promised date and the invoice's real state, so it can't disagree with the
  payment records.
"""

import copy
from datetime import date, datetime, time, timedelta, timezone

# The app always uses Malaysia time (UTC+8, no daylight saving). The server itself runs on UTC,
# so plain my_today() would show yesterday between 00:00 and 08:00 in Malaysia.
MY_TZ = timezone(timedelta(hours=8))


def my_now():
    return datetime.now(MY_TZ).replace(tzinfo=None)


def my_today():
    return datetime.now(MY_TZ).date()


TODAY = my_today()


def _days(n):
    """A date n days from today (negative = in the past)."""
    return TODAY + timedelta(days=n)


# --- Synthetic customers ------------------------------------------------
# preferred_language: the language this customer usually does business in
# ("en" English, "ms" Bahasa Malaysia, "zh" Chinese).

CUSTOMERS = [
    {"id": 1, "name": "Aiman Hardware Supplies", "phone": "+60 12-345 0101", "preferred_language": "ms"},
    {"id": 2, "name": "Mei Ling Bakery", "phone": "+60 16-789 0202", "preferred_language": "zh"},
    {"id": 3, "name": "Thiru Auto Parts", "phone": "+60 11-2345 0303", "preferred_language": "en"},
    {"id": 4, "name": "Siti's Boutique", "phone": "+60 13-456 0404", "preferred_language": "ms"},
    {"id": 5, "name": "Chong Electrical Services", "phone": "+60 17-890 0505", "preferred_language": "zh"},
    {"id": 6, "name": "Farah Catering Co.", "phone": "+60 18-234 0606", "preferred_language": "en"},
]
CUSTOMERS_BY_ID = {c["id"]: c for c in CUSTOMERS}


def _invoice(id, invoice_no, customer_id, amount, due, status="Unpaid", paid=None, reminded=None):
    return {
        "id": id,
        "invoice_no": invoice_no,
        "customer_id": customer_id,
        "amount": amount,
        "due_date": _days(due),
        "status": status,
        "paid_date": _days(paid) if paid is not None else None,
        "last_reminded": _days(reminded) if reminded is not None else None,
    }


# --- Synthetic invoices -------------------------------------------------
# Open invoices first (ids 1-5), then Farah's paid one (6), then older PAID
# invoices (7-15) that make up each customer's payment history.

INVOICES = [
    _invoice(1, "INV-2026-0038", 1, 1250.00, due=-3),
    _invoice(2, "INV-2026-0031", 2, 480.50, due=-14),
    _invoice(3, "INV-2026-0044", 3, 2100.00, due=5),
    _invoice(4, "INV-2026-0040", 4, 320.00, due=-1),
    _invoice(5, "INV-2026-0027", 5, 875.00, due=-21),
    _invoice(6, "INV-2026-0035", 6, 640.00, due=-5, status="Paid", paid=-3, reminded=-4),
    # payment history (all paid)
    _invoice(7, "INV-2026-0012", 5, 640.00, due=-120, status="Paid", paid=-105),
    _invoice(8, "INV-2026-0018", 5, 910.00, due=-90, status="Paid", paid=-70),
    _invoice(9, "INV-2026-0022", 5, 450.00, due=-60, status="Paid", paid=-48),
    _invoice(10, "INV-2026-0014", 2, 380.00, due=-100, status="Paid", paid=-88),
    _invoice(11, "INV-2026-0021", 2, 520.00, due=-62, status="Paid", paid=-53),
    _invoice(12, "INV-2026-0019", 4, 275.00, due=-75, status="Paid", paid=-70),
    _invoice(13, "INV-2026-0016", 1, 1100.00, due=-80, status="Paid", paid=-82),
    _invoice(14, "INV-2026-0017", 3, 1950.00, due=-70, status="Paid", paid=-73),
    _invoice(15, "INV-2026-0010", 6, 580.00, due=-45, status="Paid", paid=-47),
]


def late_payment_count(customer_id):
    """Earlier late payments = this customer's PAID invoices paid after the due date."""
    return sum(
        1 for inv in INVOICES
        if inv["customer_id"] == customer_id
        and inv["status"] == "Paid"
        and inv["paid_date"] is not None
        and inv["paid_date"] > inv["due_date"]
    )


def _sync_customer_fields():
    """Fill each invoice's convenience fields from CUSTOMERS and the payment records."""
    for inv in INVOICES:
        customer = CUSTOMERS_BY_ID[inv["customer_id"]]
        inv["customer_name"] = customer["name"]
        inv["phone"] = customer["phone"]
        inv["preferred_language"] = customer["preferred_language"]
        inv["past_late_count"] = late_payment_count(inv["customer_id"])


_sync_customer_fields()


# --- Activity log -------------------------------------------------------

def get_invoice_by_id(invoice_id):
    for inv in INVOICES:
        if inv["id"] == invoice_id:
            return inv
    return None


def get_customer(customer_id):
    return CUSTOMERS_BY_ID.get(customer_id)


def _seed_entry(days_ago, hour, invoice_id, invoice_no, customer_name, message, risk_tier, language):
    when = my_now().replace(hour=hour, minute=15, second=0, microsecond=0) - timedelta(days=days_ago)
    invoice = get_invoice_by_id(invoice_id) if invoice_id else None
    return {
        "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
        "invoice_id": invoice_id,
        "invoice_no": invoice_no,
        "customer_id": invoice["customer_id"] if invoice else None,
        "customer_name": customer_name,
        "message_sent": message,
        "risk_tier": risk_tier,
        "language": language,
        "approved_by": "Owner",
    }


# Logs every reminder that a human has approved and "sent" (sending is simulated).
#
# Starts with a few SYNTHETIC past entries so the dashboard KPIs and the
# Activity Log are not empty on first load (this is demo history, not real data).
# The last two are for customers that are not in this SME's customer list, so
# they have no customer_id and do not appear on any Customer page.
ACTIVITY_LOG = [
    _seed_entry(
        4, 10, 6, "INV-2026-0035", "Farah Catering Co.",
        "Hi Farah Catering Co., just a friendly reminder that invoice INV-2026-0035 "
        "(RM640.00) is now overdue. Could you let us know when we can expect payment? "
        "Thank you! — Accounts Team",
        "low", "en",
    ),
    _seed_entry(
        3, 15, None, "INV-2026-0029", "Lim Stationery",
        "Lim Stationery 您好，关于发票 INV-2026-0029（RM530.00），现已逾期 9 天。"
        "请尽快安排付款；如有任何问题，也请及时与我们联系。— 财务部",
        "medium", "zh",
    ),
    _seed_entry(
        2, 11, None, "INV-2026-0033", "Kumar Motors",
        "Hai Kumar Motors, ini peringatan mesra bahawa invois INV-2026-0033 (RM410.00) "
        "telah tamat tempoh 2 hari yang lalu. Bolehkah anda maklumkan bila pembayaran "
        "boleh dibuat? Terima kasih! — Pasukan Akaun",
        "low", "ms",
    ),
]

# --- Payment promises ---------------------------------------------------
# A promise = "this customer said they will pay this invoice on this date".
# Newest promise on an invoice is the one that counts; older ones stay as history.

PROMISE_MAX_DAYS = 60   # a promised date further away than this is rejected
PROMISE_NOTE_MAX = 120


def _seed_promise(id, invoice_id, promised_in_days, created_days_ago, note):
    invoice = get_invoice_by_id(invoice_id)
    created = my_now().replace(hour=14, minute=30, second=0, microsecond=0) - timedelta(days=created_days_ago)
    return {
        "id": id,
        "invoice_id": invoice_id,
        "customer_id": invoice["customer_id"],
        "promised_date": _days(promised_in_days),
        "note": note,
        "created": created.strftime("%Y-%m-%d %H:%M:%S"),
    }


# SYNTHETIC demo promises, so the feature is visible on first load:
#  - Mei Ling Bakery promised a date that has already passed (a broken promise)
#  - Siti's Boutique promised a date two days from now (still pending)
PROMISES = [
    _seed_promise(1, 2, promised_in_days=-2, created_days_ago=6,
                  note="Said she would transfer after the weekend."),
    _seed_promise(2, 4, promised_in_days=2, created_days_ago=0,
                  note="Will pay once her own customer settles."),
]

# A copy of the starting state, so the demo can be put back exactly as it began.
_STARTING_INVOICES = copy.deepcopy(INVOICES)
_STARTING_LOG = copy.deepcopy(ACTIVITY_LOG)
_STARTING_PROMISES = copy.deepcopy(PROMISES)

# Invoices that were marked paid during this run (invoice id -> status before).
# Only these can be undone; the paid history that came with the demo data stays.
_PAID_IN_SESSION = {}


def mark_overdue_invoices():
    """
    TRIGGER step of the automation journey.

    Scans all invoices and flags any that are past their due date and still
    unpaid (including ones we already reminded once — they are still owed).
    Returns the list of overdue invoices.

    In a real deployment this would run on a schedule (e.g. daily cron job).
    For the live demo we trigger it manually via a button, so judges can see
    the exact moment the automation fires.
    """
    _sync_customer_fields()
    overdue = []
    today = my_today()
    for inv in INVOICES:
        if inv["status"] in ("Unpaid", "Reminded") and inv["due_date"] < today:
            inv["days_overdue"] = (today - inv["due_date"]).days
            overdue.append(inv)
    return overdue


# Receivables ageing buckets (days past due) — the standard accounting view of
# "how old is the money we are still owed".
AGEING_BUCKETS = [
    ("1–7 days", 1, 7),
    ("8–14 days", 8, 14),
    ("15–30 days", 15, 30),
    ("30+ days", 31, 10**6),
]


def ageing_summary(overdue):
    """Groups overdue invoices into ageing buckets: count + total RM each."""
    summary = []
    for label, low, high in AGEING_BUCKETS:
        items = [inv for inv in overdue if low <= inv["days_overdue"] <= high]
        summary.append({
            "label": label,
            "count": len(items),
            "amount": sum(inv["amount"] for inv in items),
        })
    return summary


def log_activity(invoice_id, customer_name, message_sent, risk_tier="", language="", approved_by="Owner"):
    """OUTCOME step: records a human-approved action, so it stays visible and auditable.

    risk_tier records what ChaseFlow had recommended (low/medium/high) at the
    time this reminder was approved, and language records which language the
    message was written in — part of the audit trail, not just the text itself.

    It also moves the invoice to "Reminded", so the owner can see at a glance
    which overdue customers have already been chased.
    """
    invoice = get_invoice_by_id(invoice_id)
    entry = {
        "timestamp": my_now().strftime("%Y-%m-%d %H:%M:%S"),
        "invoice_id": invoice_id,
        "invoice_no": invoice["invoice_no"] if invoice else "",
        "customer_id": invoice["customer_id"] if invoice else None,
        "customer_name": customer_name,
        "message_sent": message_sent,
        "risk_tier": risk_tier,
        "language": language,
        "approved_by": approved_by,
    }
    ACTIVITY_LOG.append(entry)

    if invoice is not None and invoice["status"] != "Paid":
        invoice["status"] = "Reminded"
        invoice["last_reminded"] = my_today()
    return entry


def mark_paid(invoice_id):
    """Closes the loop: the customer paid, so the invoice leaves the overdue list.

    The payment date is recorded, so if it is after the due date this counts
    as a late payment on the customer's record from now on."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return False
    if invoice["status"] != "Paid":
        _PAID_IN_SESSION[invoice_id] = invoice["status"]
        invoice["status"] = "Paid"
        invoice["paid_date"] = my_today()
    _sync_customer_fields()
    return True


def can_undo_paid(invoice_id):
    """Only a payment marked during this run can be undone."""
    return invoice_id in _PAID_IN_SESSION


def mark_unpaid(invoice_id):
    """Undo a 'Mark as paid' (for example it was clicked by mistake).

    The invoice goes back to the status it had before, and the payment date
    is removed, so it no longer counts on the customer's payment record."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None or invoice_id not in _PAID_IN_SESSION:
        return False
    invoice["status"] = _PAID_IN_SESSION.pop(invoice_id)
    invoice["paid_date"] = None
    _sync_customer_fields()
    return True


def reset_demo_data():
    """Puts the synthetic invoices, activity log and promises back to the way they
    started. Edits the lists in place, because other modules hold references."""
    INVOICES[:] = copy.deepcopy(_STARTING_INVOICES)
    ACTIVITY_LOG[:] = copy.deepcopy(_STARTING_LOG)
    PROMISES[:] = copy.deepcopy(_STARTING_PROMISES)
    _PAID_IN_SESSION.clear()
    _sync_customer_fields()


# --- Payment promises: logic --------------------------------------------

PROMISE_LABELS = {
    "pending": "Promised",
    "kept": "Kept",
    "paid_late": "Paid late",
    "broken": "Broken",
    "replaced": "Replaced",
}


def promise_status(promise):
    """Worked out from facts, never stored:
      kept       invoice paid on or before the promised date
      paid_late  invoice paid, but after the promised date
      broken     promised date has passed and the invoice is still unpaid
      replaced   a newer promise was recorded and this date has not passed yet
      pending    promised date is today or later, and no newer promise exists"""
    invoice = get_invoice_by_id(promise["invoice_id"])
    if invoice["status"] == "Paid" and invoice["paid_date"] is not None:
        return "kept" if invoice["paid_date"] <= promise["promised_date"] else "paid_late"
    if promise["promised_date"] < my_today():
        return "broken"
    newer = any(p["invoice_id"] == promise["invoice_id"] and p["id"] > promise["id"] for p in PROMISES)
    return "replaced" if newer else "pending"


def _with_status(promise):
    invoice = get_invoice_by_id(promise["invoice_id"])
    status = promise_status(promise)
    days_to_go = (promise["promised_date"] - my_today()).days
    return {
        **promise,
        "status": status,
        "label": PROMISE_LABELS[status],
        "invoice": invoice,
        "days_to_go": days_to_go,
        "created_dt": datetime.strptime(promise["created"], "%Y-%m-%d %H:%M:%S"),
    }


def promises_for_invoice(invoice_id):
    """Every promise on one invoice, newest first."""
    items = [_with_status(p) for p in PROMISES if p["invoice_id"] == invoice_id]
    return sorted(items, key=lambda p: p["id"], reverse=True)


def latest_promise(invoice_id):
    items = promises_for_invoice(invoice_id)
    return items[0] if items else None


def all_promises():
    """Every recorded promise, newest first (for the Activity Log page)."""
    return sorted((_with_status(p) for p in PROMISES), key=lambda p: p["id"], reverse=True)


def customer_promises(customer_id):
    items = [_with_status(p) for p in PROMISES if p["customer_id"] == customer_id]
    return sorted(items, key=lambda p: p["id"], reverse=True)


def promise_stats(customer_id):
    items = customer_promises(customer_id)
    return {
        "total": len(items),
        "kept": sum(1 for p in items if p["status"] == "kept"),
        "missed": sum(1 for p in items if p["status"] in ("broken", "paid_late")),
        "pending": sum(1 for p in items if p["status"] == "pending"),
    }


def promise_context(invoice):
    """What the promise history means for the next chase of this invoice.

    Returns None when the customer has made no promise on it. Otherwise:
      latest  the newest promise (with status)
      missed  how many promises this customer has missed in total
      hint    one rule-based sentence of advice for the owner (no AI)
      ai_text the plain facts handed to the AI, so its draft can refer to them"""
    latest = latest_promise(invoice["id"])
    if latest is None:
        return None
    missed = promise_stats(invoice["customer_id"])["missed"]
    when = latest["promised_date"].strftime("%d %b %Y")
    ago = -latest["days_to_go"]

    if latest["status"] == "broken":
        hint = (f"Broken promise: the customer said they would pay on {when} "
                f"({ago} day{'s' if ago != 1 else ''} ago) and has not. Follow up firmly and refer to that date.")
        ai_text = (f"The customer promised to pay on {when}, {ago} day(s) ago, but payment has not arrived.")
    elif latest["status"] == "pending":
        hint = (f"Open promise: the customer said they will pay on {when}. "
                f"Consider waiting until then before chasing again.")
        ai_text = f"The customer has promised to pay on {when}."
    else:
        hint = ""
        ai_text = ""
    if ai_text and missed:
        ai_text += f" This customer has missed {missed} payment promise(s) in total."
    return {"latest": latest, "missed": missed, "hint": hint, "ai_text": ai_text}


def log_promise(invoice_id, promised_date_text, note=""):
    """Records "customer promised to pay on <date>" for one unpaid invoice.

    Returns (promise, None) on success or (None, plain-English error).
    The date must be today or later and no more than PROMISE_MAX_DAYS away."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return None, "Invoice not found."
    if invoice["status"] == "Paid":
        return None, "This invoice is already paid, so there is nothing to promise."
    try:
        promised = datetime.strptime((promised_date_text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None, "Please choose a valid date."
    today = my_today()
    if promised < today:
        return None, "The promised date cannot be in the past."
    if promised > today + timedelta(days=PROMISE_MAX_DAYS):
        return None, f"The promised date must be within {PROMISE_MAX_DAYS} days from today."

    promise = {
        "id": max((p["id"] for p in PROMISES), default=0) + 1,
        "invoice_id": invoice_id,
        "customer_id": invoice["customer_id"],
        "promised_date": promised,
        "note": " ".join((note or "").split())[:PROMISE_NOTE_MAX],
        "created": my_now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    PROMISES.append(promise)
    return promise, None


def promise_overview():
    """Dashboard-style totals over open invoices, using each invoice's newest promise."""
    pending, broken = [], []
    for inv in INVOICES:
        if inv["status"] == "Paid":
            continue
        latest = latest_promise(inv["id"])
        if latest is None:
            continue
        if latest["status"] == "pending":
            pending.append(latest)
        elif latest["status"] == "broken":
            broken.append(latest)
    return {
        "pending_count": len(pending),
        "pending_amount": sum(p["invoice"]["amount"] for p in pending),
        "broken_count": len(broken),
        "broken_amount": sum(p["invoice"]["amount"] for p in broken),
    }


# --- Customer views -----------------------------------------------------
# Everything below is computed from CUSTOMERS, INVOICES and ACTIVITY_LOG.
# Nothing is stored twice and no history is invented.

def is_overdue(invoice):
    return invoice["status"] in ("Unpaid", "Reminded") and invoice["due_date"] < my_today()


def _log_time(entry):
    return datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")


def customer_invoices(customer_id):
    return [inv for inv in INVOICES if inv["customer_id"] == customer_id]


def payment_records(customer_id):
    """Paid invoices with how many days after (positive) or before (negative) the due date they were paid."""
    records = []
    for inv in customer_invoices(customer_id):
        if inv["status"] == "Paid" and inv["paid_date"] is not None:
            records.append({
                "invoice": inv,
                "days_late": (inv["paid_date"] - inv["due_date"]).days,
            })
    records.sort(key=lambda r: r["invoice"]["paid_date"], reverse=True)
    return records


def customer_summary(customer_id):
    """Money, overdue and payment-record facts for one customer."""
    customer = get_customer(customer_id)
    if customer is None:
        return None
    _sync_customer_fields()
    today = my_today()

    invoices = customer_invoices(customer_id)
    open_invoices = [i for i in invoices if i["status"] in ("Unpaid", "Reminded")]
    overdue = [i for i in open_invoices if i["due_date"] < today]
    for inv in overdue:
        inv["days_overdue"] = (today - inv["due_date"]).days

    records = payment_records(customer_id)
    late_days = [r["days_late"] for r in records if r["days_late"] > 0]
    entries = [e for e in ACTIVITY_LOG if e.get("customer_id") == customer_id]
    last_followup = max((_log_time(e) for e in entries), default=None)

    return {
        "customer": customer,
        "open_invoices": sorted(open_invoices, key=lambda i: i["due_date"]),
        "overdue_invoices": overdue,
        "outstanding": sum(i["amount"] for i in open_invoices),
        "overdue_amount": sum(i["amount"] for i in overdue),
        "paid_count": len(records),
        "late_count": len(late_days),
        "on_time_count": len(records) - len(late_days),
        "avg_days_late": round(sum(late_days) / len(late_days), 1) if late_days else None,
        "records": records,
        "last_followup": last_followup,
        "reminder_count": len(entries),
    }


def customer_timeline(customer_id):
    """Events the system has actually recorded for this customer, newest first:
    reminders a human approved (Activity Log), payment promises, and invoices marked paid."""
    events = []
    for entry in ACTIVITY_LOG:
        if entry.get("customer_id") == customer_id:
            events.append({
                "when": _log_time(entry),
                "kind": "reminder",
                "title": f"Reminder approved for {entry['invoice_no']}",
                "detail": entry["message_sent"],
                "risk": entry["risk_tier"],
                "language": entry["language"],
            })
    for rec in payment_records(customer_id):
        inv = rec["invoice"]
        late = rec["days_late"]
        if late > 0:
            note = f"Paid {late} day{'s' if late != 1 else ''} after the due date"
        elif late == 0:
            note = "Paid on the due date"
        else:
            note = f"Paid {-late} day{'s' if -late != 1 else ''} before the due date"
        events.append({
            "when": datetime.combine(inv["paid_date"], time(12, 0)),
            "kind": "paid",
            "title": f"{inv['invoice_no']} paid · RM {inv['amount']:,.2f}",
            "detail": note,
            "risk": "",
            "language": "",
        })
    for p in customer_promises(customer_id):
        inv = p["invoice"]
        when = p["promised_date"].strftime("%d %b %Y")
        if p["status"] == "kept":
            outcome = f"Kept: paid on {inv['paid_date']}"
        elif p["status"] == "paid_late":
            outcome = f"Paid late: paid on {inv['paid_date']}, after the promised date"
        elif p["status"] == "broken":
            outcome = "Broken: promised date passed and the invoice is still unpaid"
        elif p["status"] == "replaced":
            outcome = "Replaced by a newer promise"
        else:
            outcome = "Waiting: the promised date has not arrived yet"
        detail = f"{outcome}. {p['note']}" if p["note"] else outcome
        events.append({
            "when": p["created_dt"],
            "kind": "promise",
            "title": f"Promised to pay {inv['invoice_no']} by {when}",
            "detail": detail,
            "risk": "",
            "language": "",
        })
    events.sort(key=lambda e: e["when"], reverse=True)
    return events