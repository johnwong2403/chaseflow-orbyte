"""
In-memory data layer for the ChaseFlow MVP.

Why in-memory instead of a real database for the prototype:
- Our deadline is a few days away; a real DB (Postgres/SQLite file) adds setup
  risk for no judging benefit at this stage.
- All data here is SYNTHETIC (made up), per competition rules — no real SME
  or customer data is used anywhere in this project. Phone numbers are fake.

If this were a production Orbyte module, this file is exactly where a real
database (e.g. SQLite/Postgres via SQLAlchemy) would replace the Python list.
In Orbyte terms: customer details (phone, preferred language) would come from
the People module, and invoices + payment history from the Connect module.

Invoice status lifecycle:
    Unpaid  --(owner approves a reminder)-->  Reminded  --(payment received)-->  Paid
"""

from datetime import date, datetime, timedelta

# --- Synthetic seed data -----------------------------------------------
# Represents invoices an SME has issued to its customers.
#   past_late_count    simulates that customer's payment history with this SME
#   preferred_language the language this customer usually does business in
#                      ("en" English, "ms" Bahasa Malaysia, "zh" Chinese)
#   last_reminded      None until the owner approves a reminder for the invoice

INVOICES = [
    {
        "id": 1,
        "invoice_no": "INV-2026-0038",
        "customer_name": "Aiman Hardware Supplies",
        "phone": "+60 12-345 0101",
        "preferred_language": "ms",
        "amount": 1250.00,
        "due_date": date.today() - timedelta(days=3),
        "status": "Unpaid",
        "past_late_count": 0,
        "last_reminded": None,
    },
    {
        "id": 2,
        "invoice_no": "INV-2026-0031",
        "customer_name": "Mei Ling Bakery",
        "phone": "+60 16-789 0202",
        "preferred_language": "zh",
        "amount": 480.50,
        "due_date": date.today() - timedelta(days=14),
        "status": "Unpaid",
        "past_late_count": 2,
        "last_reminded": None,
    },
    {
        "id": 3,
        "invoice_no": "INV-2026-0044",
        "customer_name": "Thiru Auto Parts",
        "phone": "+60 11-2345 0303",
        "preferred_language": "en",
        "amount": 2100.00,
        "due_date": date.today() + timedelta(days=5),
        "status": "Unpaid",
        "past_late_count": 0,
        "last_reminded": None,
    },
    {
        "id": 4,
        "invoice_no": "INV-2026-0040",
        "customer_name": "Siti's Boutique",
        "phone": "+60 13-456 0404",
        "preferred_language": "ms",
        "amount": 320.00,
        "due_date": date.today() - timedelta(days=1),
        "status": "Unpaid",
        "past_late_count": 1,
        "last_reminded": None,
    },
    {
        "id": 5,
        "invoice_no": "INV-2026-0027",
        "customer_name": "Chong Electrical Services",
        "phone": "+60 17-890 0505",
        "preferred_language": "zh",
        "amount": 875.00,
        "due_date": date.today() - timedelta(days=21),
        "status": "Unpaid",
        "past_late_count": 3,
        "last_reminded": None,
    },
    {
        "id": 6,
        "invoice_no": "INV-2026-0035",
        "customer_name": "Farah Catering Co.",
        "phone": "+60 18-234 0606",
        "preferred_language": "en",
        "amount": 640.00,
        "due_date": date.today() - timedelta(days=5),
        "status": "Paid",
        "past_late_count": 0,
        "last_reminded": date.today() - timedelta(days=4),
    },
]


def _seed_entry(days_ago, hour, invoice_id, invoice_no, customer_name, message, risk_tier, language):
    when = datetime.now().replace(hour=hour, minute=15, second=0, microsecond=0) - timedelta(days=days_ago)
    return {
        "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
        "invoice_id": invoice_id,
        "invoice_no": invoice_no,
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


def get_invoice_by_id(invoice_id):
    for inv in INVOICES:
        if inv["id"] == invoice_id:
            return inv
    return None


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
    """Closes the loop: the customer paid, so the invoice leaves the overdue list."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return False
    invoice["status"] = "Paid"
    return True