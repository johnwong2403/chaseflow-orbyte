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

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, redirect, url_for, request

from data import INVOICES, ACTIVITY_LOG, mark_overdue_invoices, get_invoice_by_id, log_activity
from reminder_ai import generate_reminder_draft, assess_invoice_risk

app = Flask(__name__)


@app.route("/")
def dashboard():
    return render_template("dashboard.html", invoices=INVOICES)


@app.route("/check-overdue")
def check_overdue():
    overdue = mark_overdue_invoices()
    for inv in overdue:
        inv["risk"] = assess_invoice_risk(inv)
    risk_order = {"high": 0, "medium": 1, "low": 2}
    overdue.sort(key=lambda inv: risk_order[inv["risk"]["risk_tier"]])
    return render_template("review.html", overdue=overdue)


@app.route("/draft/<int:invoice_id>")
def draft_reminder(invoice_id):
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return "Invoice not found", 404
    draft = generate_reminder_draft(invoice)
    return render_template("draft.html", invoice=invoice, draft=draft)


@app.route("/approve/<int:invoice_id>", methods=["POST"])
def approve_reminder(invoice_id):
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return "Invoice not found", 404

    final_message = request.form.get("message", "")
    risk_tier = request.form.get("risk_tier", "")
    log_activity(invoice_id, invoice["customer_name"], final_message, risk_tier=risk_tier)

    return redirect(url_for("activity_log"))


@app.route("/activity-log")
def activity_log():
    return render_template("activity_log.html", logs=list(reversed(ACTIVITY_LOG)))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)