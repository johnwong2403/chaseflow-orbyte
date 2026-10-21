"""
In-memory data layer for the ChaseFlow MVP.

Why in-memory instead of a real database for the prototype:
- Our deadline is a few days away; a real DB (Postgres/SQLite file) adds setup
  risk for no judging benefit at this stage.
- All data here is SYNTHETIC (made up), per competition rules — no real SME
  or customer data is used anywhere in this project.

If this were a production Orbyte module, this file is exactly where a real
database (e.g. SQLite/Postgres via SQLAlchemy) would replace the Python list.

Invoice status lifecycle:
    Unpaid  --(owner approves a reminder)-->  Reminded  --(payment received)-->  Paid
"""

from datetime import date, datetime, timedelta

# --- Synthetic seed data -----------------------------------------------
# Represents invoices/quotations a small SME has issued to its customers.
# past_late_count simulates that customer's payment history with this SME.
# last_reminded is None until the owner approves a reminder for that invoice.

INVOICES = [
    {
        "id": 1,
        "customer_name": "Aiman Hardware Supplies",
        "amount": 1250.00,
        "due_date": date.today() - timedelta(days=3),
        "status": "Unpaid",
        "past_late_count": 0,
        "last_reminded": None,
    },
    {
        "id": 2,
        "customer_name": "Mei Ling Bakery",
        "amount": 480.50,
        "due_date": date.today() - timedelta(days=14),
        "status": "Unpaid",
        "past_late_count": 2,
        "last_reminded": None,
    },
    {
        "id": 3,
        "customer_name": "Thiru Auto Parts",
        "amount": 2100.00,
        "due_date": date.today() + timedelta(days=5),
        "status": "Unpaid",
        "past_late_count": 0,
        "last_reminded": None,
    },
    {
        "id": 4,
        "customer_name": "Siti's Boutique",
        "amount": 320.00,
        "due_date": date.today() - timedelta(days=1),
        "status": "Unpaid",
        "past_late_count": 1,
        "last_reminded": None,
    },
    {
        "id": 5,
        "customer_name": "Chong Electrical Services",
        "amount": 875.00,
        "due_date": date.today() - timedelta(days=21),
        "status": "Unpaid",
        "past_late_count": 3,
        "last_reminded": None,
    },
    {
        "id": 6,
        "customer_name": "Farah Catering Co.",
        "amount": 640.00,
        "due_date": date.today() - timedelta(days=5),
        "status": "Paid",
        "past_late_count": 0,
        "last_reminded": date.today() - timedelta(days=4),
    },
]


def _seed_entry(days_ago, hour, invoice_id, customer_name, message, risk_tier):
    when = datetime.now().replace(hour=hour, minute=15, second=0, microsecond=0) - timedelta(days=days_ago)
    return {
        "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
        "invoice_id": invoice_id,
        "customer_name": customer_name,
        "message_sent": message,
        "risk_tier": risk_tier,
        "approved_by": "Owner",
    }


# Logs every reminder that a human has approved and "sent".
# Each entry: timestamp, invoice_id, customer_name, message_sent, risk_tier, approved_by
#
# Starts with a few SYNTHETIC past entries so the dashboard KPIs and the
# Activity Log are not empty on first load (this is demo history, not real data).
ACTIVITY_LOG = [
    _seed_entry(
        4, 10, 6, "Farah Catering Co.",
        "Hi Farah Catering Co., just a friendly reminder that your invoice for RM640.00 "
        "is now overdue. Could you let us know when we can expect payment? Thank you!",
        "low",
    ),
    _seed_entry(
        3, 15, None, "Lim Stationery",
        "Dear Lim Stationery, this is a follow-up on your outstanding invoice of RM530.00, "
        "now 9 days overdue. Please arrange payment as soon as possible.",
        "medium",
    ),
    _seed_entry(
        2, 11, None, "Kumar Motors",
        "Hi Kumar Motors, a quick reminder that your invoice for RM410.00 was due 2 days ago. "
        "Please let us know when payment will be made. Thank you!",
        "low",
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


def log_activity(invoice_id, customer_name, message_sent, risk_tier="", approved_by="Owner"):
    """OUTCOME step: records a human-approved action, so it stays visible and auditable.

    risk_tier records what ChaseFlow had recommended (low/medium/high) at the
    time this reminder was approved — part of the audit trail, not just the
    message text itself.

    It also moves the invoice to "Reminded", so the owner can see at a glance
    which overdue customers have already been chased.
    """
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "invoice_id": invoice_id,
        "customer_name": customer_name,
        "message_sent": message_sent,
        "risk_tier": risk_tier,
        "approved_by": approved_by,
    }
    ACTIVITY_LOG.append(entry)

    invoice = get_invoice_by_id(invoice_id)
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