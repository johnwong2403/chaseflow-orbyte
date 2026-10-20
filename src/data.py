"""
In-memory data layer for the ChaseFlow MVP.

Why in-memory instead of a real database for the prototype:
- Our deadline is a few days away; a real DB (Postgres/SQLite file) adds setup
  risk for no judging benefit at this stage.
- All data here is SYNTHETIC (made up), per competition rules — no real SME
  or customer data is used anywhere in this project.
"""

from datetime import date, timedelta

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

ACTIVITY_LOG = []


def get_invoice_by_id(invoice_id):
    for inv in INVOICES:
        if inv["id"] == invoice_id:
            return inv
    return None


def mark_overdue_invoices():
    """
    TRIGGER step. Finds invoices that are unpaid and past due date.
    Demo uses a manual button instead of a real daily schedule,
    so judges see the exact moment the automation fires.
    """
    overdue = []
    today = date.today()
    for inv in INVOICES:
        if inv["status"] == "Unpaid" and inv["due_date"] < today:
            inv["days_overdue"] = (today - inv["due_date"]).days
            overdue.append(inv)
    return overdue


def log_activity(invoice_id, customer_name, message_sent, risk_tier="N/A", approved_by="Owner"):
    """OUTCOME step: records a human-approved action, so it stays visible and auditable."""
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