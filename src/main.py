"""
ChaseFlow for Orbyte — Flask entry point.

A small automation tool for micro/small SMEs: finds overdue invoices,
drafts a tone-appropriate follow-up reminder, and only sends it after a
human approves — then logs the outcome.

Automation journey (required by Domain 2):
  TRIGGER (check overdue) -> DATA (invoice + customer history)
  -> LOGIC (risk tier + draft message) -> APPROVAL (human clicks Approve)
  -> OUTCOME (logged + visible in Activity Log)
"""

import os
import sys
from datetime import datetime, timedelta

# allow "from data import ..." style imports when run directly
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, redirect, url_for, request

from data import (
    INVOICES,
    ACTIVITY_LOG,
    mark_overdue_invoices,
    get_invoice_by_id,
    log_activity,
    mark_paid,
)
from reminder_ai import generate_reminder_draft, assess_invoice_risk

# main.py lives in src/, but templates/ and static/ live one level up, at the
# project root — point Flask there explicitly instead of relying on its
# default (which looks next to this file, inside src/).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(PROJECT_ROOT, "templates"),
    static_folder=os.path.join(PROJECT_ROOT, "static"),
)


@app.route("/")
def dashboard():
    """Shows every invoice plus live KPI stats — the measurable business
    benefit the PRD asks for, computed fresh from the current data."""
    overdue = mark_overdue_invoices()

    total_overdue = sum(inv["amount"] for inv in overdue)
    high_risk_count = sum(
        1 for inv in overdue if assess_invoice_risk(inv)["risk_tier"] == "high"
    )
    avg_days_overdue = (
        round(sum(inv["days_overdue"] for inv in overdue) / len(overdue), 1)
        if overdue else 0
    )
    cutoff = datetime.now() - timedelta(days=7)
    reminders_7d = sum(
        1 for log in ACTIVITY_LOG
        if datetime.strptime(log["timestamp"], "%Y-%m-%d %H:%M:%S") >= cutoff
    )

    return render_template(
        "dashboard.html",
        invoices=INVOICES,
        total_overdue=total_overdue,
        high_risk_count=high_risk_count,
        avg_days_overdue=avg_days_overdue,
        reminders_7d=reminders_7d,
    )


@app.route("/check-overdue")
def check_overdue():
    """TRIGGER step — scans invoices, then DECISION LOGIC assigns each one
    a risk tier so the owner can see what matters most before acting."""
    overdue = mark_overdue_invoices()
    for inv in overdue:
        inv["risk"] = assess_invoice_risk(inv)
    risk_order = {"high": 0, "medium": 1, "low": 2}
    overdue.sort(key=lambda inv: risk_order[inv["risk"]["risk_tier"]])
    return render_template("review.html", overdue=overdue)


@app.route("/draft/<int:invoice_id>")
def draft_reminder(invoice_id):
    """LOGIC step — generates an editable AI draft (risk tier + recommended
    action + message text) for one overdue invoice."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return "Invoice not found", 404
    mark_overdue_invoices()  # makes sure days_overdue is filled in for this invoice
    draft = generate_reminder_draft(invoice)
    return render_template("draft.html", invoice=invoice, draft=draft)


@app.route("/approve/<int:invoice_id>", methods=["POST"])
def approve_reminder(invoice_id):
    """APPROVAL + OUTCOME step — human approves (optionally edited) text,
    we 'send' it (simulated) and log it, including which risk tier and tone
    ChaseFlow had recommended, so the Activity Log stays fully auditable."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return "Invoice not found", 404

    final_message = request.form.get("message", "")
    risk_tier = request.form.get("risk_tier", "")
    log_activity(invoice_id, invoice["customer_name"], final_message, risk_tier=risk_tier)

    return redirect(url_for("activity_log"))


@app.route("/mark-paid/<int:invoice_id>", methods=["POST"])
def mark_invoice_paid(invoice_id):
    """Closes the loop: customer paid, invoice leaves the overdue list."""
    if not mark_paid(invoice_id):
        return "Invoice not found", 404
    return redirect(url_for("dashboard"))


@app.route("/activity-log")
def activity_log():
    """OUTCOME step — every approved reminder is visible here, auditable."""
    return render_template("activity_log.html", logs=list(reversed(ACTIVITY_LOG)))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Debug mode (auto-reload + in-browser debugger) is only for local editing.
    # On a published Replit deployment REPLIT_DEPLOYMENT is set, so it stays off.
    is_deployed = bool(os.environ.get("REPLIT_DEPLOYMENT"))
    app.run(host="0.0.0.0", port=port, debug=not is_deployed)