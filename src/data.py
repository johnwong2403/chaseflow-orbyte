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
"""

import copy
from datetime import date, datetime, time, timedelta

TODAY = date.today()


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
    when = datetime.now().replace(hour=hour, minute=15, second=0, microsecond=0) - timedelta(days=days_ago)
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

# A copy of the starting state, so the demo can be put back exactly as it began.
_STARTING_INVOICES = copy.deepcopy(INVOICES)
_STARTING_LOG = copy.deepcopy(ACTIVITY_LOG)

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
    today = date.today()
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
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
        invoice["last_reminded"] = date.today()
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
        invoice["paid_date"] = date.today()
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
    """Puts the synthetic invoices and the activity log back to the way they
    started. Edits the lists in place, because other modules hold references."""
    INVOICES[:] = copy.deepcopy(_STARTING_INVOICES)
    ACTIVITY_LOG[:] = copy.deepcopy(_STARTING_LOG)
    _PAID_IN_SESSION.clear()
    _sync_customer_fields()


# --- Customer views -----------------------------------------------------
# Everything below is computed from CUSTOMERS, INVOICES and ACTIVITY_LOG.
# Nothing is stored twice and no history is invented.

def is_overdue(invoice):
    return invoice["status"] in ("Unpaid", "Reminded") and invoice["due_date"] < date.today()


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
    today = date.today()

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
    reminders a human approved (Activity Log) and invoices marked paid (payment records)."""
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
    events.sort(key=lambda e: e["when"], reverse=True)
    return events