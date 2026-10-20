"""
In-memory data layer for the ChaseFlow MVP.

Why in-memory instead of a real database for the prototype:
- Our deadline is a few days away; a real DB (Postgres/SQLite file) adds setup
  risk for no judging benefit at this stage.
- All data here is SYNTHETIC (made up), per competition rules — no real SME
  or customer data is used anywhere in this project.

If this were a production Orbyte module, this file is exactly where a real
database (e.g. SQLite/Postgres via SQLAlchemy) would replace the Python list.
"""

from datetime import date, timedelta

# --- Synthetic seed data -----------------------------------------------
# Represents invoices/quotations a small SME has issued to its customers.
# past_late_count simulates that customer's payment history with this SME.

INVOICES = [
    {
        "id": 1,
        "customer_name": "Aiman Hardware Supplies",
        "amount": 1250.00,
        "due_date": date.today() - timedelta(days=3),
        "status": "Unpaid",
        "past_late_count": 0,
    },
    {
        "id": 2,
        "customer_name": "Mei Ling Bakery",
        "amount": 480.50,
        "due_date": date.today() - timedelta(days=14),
        "status": "Unpaid",
        "past_late_count": 2,
    },
    {
        "id": 3,
        "customer_name": "Thiru Auto Parts",
        "amount": 2100.00,
        "due_date": date.today() + timedelta(days=5),
        "status": "Unpaid",
        "past_late_count": 0,
    },
    {
        "id": 4,
        "customer_name": "Siti's Boutique",
        "amount": 320.00,
        "due_date": date.today() - timedelta(days=1),
        "status": "Unpaid",
        "past_late_count": 1,
    },
    {
        "id": 5,
        "customer_name": "Chong Electrical Services",
        "amount": 875.00,
        "due_date": date.today() - timedelta(days=21),
        "status": "Unpaid",
        "past_late_count": 3,
    },
    {
        "id": 6,
        "customer_name": "Farah Catering Co.",
        "amount": 640.00,
        "due_date": date.today() - timedelta(days=5),
        "status": "Paid",
        "past_late_count": 0,
    },
]

# Logs every reminder that a human has approved and "sent".
# Each entry: timestamp, invoice_id, customer_name, message_sent, risk_tier, approved_by
ACTIVITY_LOG = []


def get_invoice_by_id(invoice_id):
    for inv in INVOICES:
        if inv["id"] == invoice_id:
            return inv
    return None


def mark_overdue_invoices():
    """
    TRIGGER step of the automation journey.

    Scans all invoices and flags any that are past their due date and still
    unpaid. Returns the list of newly-identified overdue invoices.

    In a real deployment this would run on a schedule (e.g. daily cron job).
    For the live demo we trigger it manually via a button, so judges can see
    the exact moment the automation fires.
    """
    overdue = []
    today = date.today()
    for inv in INVOICES:
        if inv["status"] == "Unpaid" and inv["due_date"] < today:
            inv["days_overdue"] = (today - inv["due_date"]).days
            overdue.append(inv)
    return overdue


def log_activity(invoice_id, customer_name, message_sent, risk_tier="", approved_by="Owner"):
    """OUTCOME step: records a human-approved action, so it stays visible and auditable.

    risk_tier records what ChaseFlow had recommended (low/medium/high) at the
    time this reminder was approved — part of the audit trail, not just the
    message text itself.
    """
    from datetime import datetime

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "invoice_id": invoice_id,
        "customer_name": customer_name,
        "message_sent": message_sent,
        "risk_tier": risk_tier,
        "approved_by": approved_by,
    }
    ACTIVITY_LOG.append(entry)
    return entry