"""
ChaseFlow for Orbyte — Flask entry point.

A small automation tool for micro/small SMEs: finds overdue invoices,
drafts a tone-appropriate follow-up reminder (in the customer's language),
and only sends it after a human approves — then logs the outcome.

Automation journey (required by Domain 2):
  TRIGGER (check overdue) -> DATA (invoice + customer history)
  -> LOGIC (risk tier + draft message) -> APPROVAL (human clicks Approve)
  -> OUTCOME (logged + visible in Activity Log)
  -> FOLLOW-UP (the customer promises a date; the app tracks whether it was kept)

Around that core journey there are supporting views, all computed from the
same data: Customers (who owes what, and their payment promises), Invoices
(every invoice), and CSV exports (so the numbers can be used in the SME's own
finance work).
"""

import csv
import io
import os
import sys
from datetime import date, datetime, timedelta

# allow "from data import ..." style imports when run directly
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, Response, abort, render_template, redirect, url_for, request

from charts import bar_chart, donut_segments
from data import (
    my_now,
    my_today,
    CUSTOMERS,
    INVOICES,
    ACTIVITY_LOG,
    PROMISE_MAX_DAYS,
    all_promises,
    mark_overdue_invoices,
    ageing_summary,
    customer_promises,
    customer_summary,
    customer_timeline,
    get_customer,
    get_invoice_by_id,
    is_overdue,
    can_undo_paid,
    latest_promise,
    log_activity,
    log_promise,
    mark_paid,
    mark_unpaid,
    promise_context,
    promise_stats,
    reset_demo_data,
)
from reminder_ai import (
    LANGUAGES,
    generate_reminder_draft,
    assess_invoice_risk,
    normalise_language,
)

# main.py lives in src/, but templates/ and static/ live one level up, at the
# project root — point Flask there explicitly instead of relying on its
# default (which looks next to this file, inside src/).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(PROJECT_ROOT, "templates"),
    static_folder=os.path.join(PROJECT_ROOT, "static"),
)

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _reminders_per_day(days=7):
    """Real counts from the Activity Log: how many reminders were approved on
    each of the last `days` days (oldest first). Used for the KPI mini chart."""
    today = my_today()
    counts = {today - timedelta(days=i): 0 for i in range(days)}
    for log in ACTIVITY_LOG:
        day = datetime.strptime(log["timestamp"], "%Y-%m-%d %H:%M:%S").date()
        if day in counts:
            counts[day] += 1
    series = [{"day": d, "label": d.strftime("%a"), "count": c} for d, c in sorted(counts.items())]
    peak = max((s["count"] for s in series), default=0) or 1
    for s in series:
        s["pct"] = round(s["count"] / peak * 100)
    return series


def _collections_insight(queue, overdue, total_overdue, avg_days):
    """A plain, rule-based summary of the highest-priority overdue invoice.

    Everything here is calculated from the invoice data — no AI call, and no
    claims the data cannot support (for example, we do not know whether a
    customer replied to an earlier reminder, so we never say so)."""
    if not queue:
        return None
    inv = queue[0]
    bullets = list(inv["risk"]["factors"])
    share = inv["amount"] / total_overdue * 100 if total_overdue else 0
    bullets.append(f"RM {inv['amount']:,.2f} is {share:.0f}% of all overdue money")
    if inv.get("last_reminded"):
        bullets.append(f"Already reminded on {inv['last_reminded']}")
    else:
        bullets.append("No reminder sent yet")
    return {"invoice": inv, "tier": inv["risk"]["risk_tier"], "bullets": bullets}


def _customer_risk(summary):
    """A customer's risk = the highest tier among their overdue invoices
    (None when nothing is overdue)."""
    tiers = [assess_invoice_risk(inv)["risk_tier"] for inv in summary["overdue_invoices"]]
    return min(tiers, key=lambda t: RISK_ORDER[t]) if tiers else None


def _safe_next(default_endpoint):
    """Where to go after a form: back to the page it came from, but only to a
    path on this same site (never an outside URL)."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//"):
        return target
    return url_for(default_endpoint)


def _csv_cell(value):
    """Stops spreadsheet programs treating text like '=1+1' as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _csv_response(filename, header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_cell(v) for v in row])
    # utf-8 with BOM so Excel shows Bahasa Malaysia and Chinese text correctly
    body = "﻿" + buffer.getvalue()
    return Response(
        body,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------

@app.route("/")
def dashboard():
    """Shows live KPI stats, receivables ageing charts and the recovery queue —
    the measurable business benefit the PRD asks for, computed fresh from
    the current data."""
    overdue = mark_overdue_invoices()
    for inv in overdue:
        inv["risk"] = assess_invoice_risk(inv)

    total_overdue = sum(inv["amount"] for inv in overdue)
    high_risk_count = sum(1 for inv in overdue if inv["risk"]["risk_tier"] == "high")
    avg_days_overdue = (
        round(sum(inv["days_overdue"] for inv in overdue) / len(overdue), 1)
        if overdue else 0
    )

    reminder_series = _reminders_per_day(7)
    reminders_7d = sum(s["count"] for s in reminder_series)

    ageing = ageing_summary(overdue)

    # days overdue per invoice, for the "Average Days Overdue" mini chart
    longest = max((i["days_overdue"] for i in overdue), default=0) or 1
    days_series = [
        {
            "label": i["customer_name"][0],
            "name": i["customer_name"],
            "days": i["days_overdue"],
            "pct": round(i["days_overdue"] / longest * 100),
        }
        for i in sorted(overdue, key=lambda i: -i["days_overdue"])
    ]

    # recovery queue: riskiest first, then biggest amount first
    ranked = sorted(overdue, key=lambda i: (RISK_ORDER[i["risk"]["risk_tier"]], -i["amount"]))

    risk_mix = []
    for tier in ("high", "medium", "low"):
        items = [i for i in overdue if i["risk"]["risk_tier"] == tier]
        amount = sum(i["amount"] for i in items)
        risk_mix.append({
            "tier": tier,
            "count": len(items),
            "amount": amount,
            "pct": round(amount / total_overdue * 100) if total_overdue else 0,
        })

    # outstanding exposure: what each customer still owes (overdue + not yet due)
    summaries = [customer_summary(c["id"]) for c in CUSTOMERS]
    exposure = sorted(
        (s for s in summaries if s["outstanding"] > 0),
        key=lambda s: -s["outstanding"],
    )[:6]
    biggest = exposure[0]["outstanding"] if exposure else 1
    exposure_rows = [
        {
            "id": s["customer"]["id"],
            "name": s["customer"]["name"],
            "outstanding": s["outstanding"],
            "overdue": s["overdue_amount"],
            "overdue_pct": round(s["overdue_amount"] / biggest * 100),
            "pct": round(s["outstanding"] / biggest * 100),
        }
        for s in exposure
    ]

    upcoming = sum(
        1 for inv in INVOICES
        if inv["status"] in ("Unpaid", "Reminded") and inv["due_date"] >= my_today()
    )
    open_invoices = sorted(
        (i for i in INVOICES if i["status"] != "Paid"), key=lambda i: i["due_date"]
    )

    activity_buckets = [
        {"label": s["label"], "count": s["count"], "amount": 0} for s in reminder_series
    ]

    return render_template(
        "dashboard.html",
        invoices=open_invoices,
        today=my_today().strftime("%a, %d %b %Y"),
        overdue_count=len(overdue),
        total_overdue=total_overdue,
        high_risk_count=high_risk_count,
        avg_days_overdue=avg_days_overdue,
        reminders_7d=reminders_7d,
        reminder_series=reminder_series,
        days_series=days_series,
        ageing=ageing,
        chart_amount=bar_chart(ageing, "amount"),
        chart_count=bar_chart(ageing, "count"),
        chart_activity=bar_chart(activity_buckets, "count", single_class="sev-0", unit="reminder", show_sub=False),
        donut=donut_segments(ageing),
        queue=ranked[:4],
        insight=_collections_insight(ranked, overdue, total_overdue, avg_days_overdue),
        risk_mix=risk_mix,
        exposure_rows=exposure_rows,
        upcoming=upcoming,
    )


# --------------------------------------------------------------------------
# core automation journey
# --------------------------------------------------------------------------

@app.route("/check-overdue")
def check_overdue():
    """TRIGGER step — scans invoices, then DECISION LOGIC assigns each one
    a risk tier so the owner can see what matters most before acting."""
    overdue = mark_overdue_invoices()
    for inv in overdue:
        inv["risk"] = assess_invoice_risk(inv)
    overdue.sort(key=lambda inv: RISK_ORDER[inv["risk"]["risk_tier"]])
    tier_counts = {
        tier: sum(1 for inv in overdue if inv["risk"]["risk_tier"] == tier)
        for tier in ("high", "medium", "low")
    }
    promises = {inv["id"]: latest_promise(inv["id"]) for inv in overdue}
    return render_template(
        "review.html",
        overdue=overdue,
        languages=LANGUAGES,
        tier_counts=tier_counts,
        promises=promises,
    )


@app.route("/draft/<int:invoice_id>")
def draft_reminder(invoice_id):
    """LOGIC step — generates an editable AI draft (risk tier + recommended
    action + message text) for one overdue invoice.

    The message language defaults to the customer's preferred language (which
    in Orbyte would come from the People module); the owner can switch it
    with ?lang=en / ms / zh and the draft is regenerated in that language."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return "Invoice not found", 404
    mark_overdue_invoices()  # makes sure days_overdue is filled in for this invoice

    language = normalise_language(request.args.get("lang") or invoice["preferred_language"])

    # If the customer has made a payment promise, the AI is told about it (as a
    # plain recorded fact). It goes in a copy, so the stored invoice is untouched.
    promise = promise_context(invoice)
    invoice_for_ai = dict(invoice)
    invoice_for_ai["promise_context"] = promise["ai_text"] if promise else ""

    draft = generate_reminder_draft(invoice_for_ai, language)
    return render_template(
        "draft.html",
        invoice=invoice,
        draft=draft,
        rule_check=assess_invoice_risk(invoice),
        promise=promise,
        languages=LANGUAGES,
        language=language,
    )


@app.route("/approve/<int:invoice_id>", methods=["POST"])
def approve_reminder(invoice_id):
    """APPROVAL + OUTCOME step — human approves (optionally edited) text,
    we 'send' it (simulated) and log it, including which risk tier and
    language ChaseFlow had used, so the Activity Log stays fully auditable."""
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        return "Invoice not found", 404

    final_message = request.form.get("message", "")
    risk_tier = request.form.get("risk_tier", "")
    language = normalise_language(request.form.get("language"))
    log_activity(
        invoice_id,
        invoice["customer_name"],
        final_message,
        risk_tier=risk_tier,
        language=language,
    )

    return redirect(url_for("activity_log"))


@app.route("/mark-paid/<int:invoice_id>", methods=["POST"])
def mark_invoice_paid(invoice_id):
    """Closes the loop: customer paid, invoice leaves the overdue list.
    Returns to the page the button was on."""
    if not mark_paid(invoice_id):
        return "Invoice not found", 404
    return redirect(_safe_next("dashboard"))


@app.route("/mark-unpaid/<int:invoice_id>", methods=["POST"])
def mark_invoice_unpaid(invoice_id):
    """Undo for a 'Mark as paid' clicked by mistake. Only works for payments
    marked during this run; the paid history in the demo data is left alone."""
    if not mark_unpaid(invoice_id):
        return "This payment cannot be undone", 400
    return redirect(_safe_next("invoices"))


@app.route("/reset-demo", methods=["POST"])
def reset_demo():
    """Puts the synthetic data back to its starting state (handy before a demo)."""
    reset_demo_data()
    return redirect(url_for("dashboard"))


@app.route("/activity-log")
def activity_log():
    """OUTCOME step — every approved reminder is visible here, auditable."""
    return render_template(
        "activity_log.html",
        logs=list(reversed(ACTIVITY_LOG)),
        promises=all_promises(),
        languages=LANGUAGES,
    )


# --------------------------------------------------------------------------
# customers
# --------------------------------------------------------------------------

@app.route("/customers")
def customers():
    """Customer directory: who owes what, how risky, and when we last followed up."""
    mark_overdue_invoices()
    rows = []
    for c in CUSTOMERS:
        summary = customer_summary(c["id"])
        rows.append({"summary": summary, "risk": _customer_risk(summary)})

    def sort_key(row):
        risk = row["risk"]
        return (RISK_ORDER[risk] if risk else 9, -row["summary"]["outstanding"])

    rows.sort(key=sort_key)
    counts = {tier: sum(1 for r in rows if r["risk"] == tier) for tier in ("high", "medium", "low")}
    counts["clear"] = sum(1 for r in rows if r["risk"] is None)
    return render_template("customers.html", rows=rows, counts=counts, languages=LANGUAGES)


def _render_customer_detail(customer_id, promise_error=None, error_invoice_id=None):
    """Builds the customer page. Also used to show a promise form error in place."""
    mark_overdue_invoices()
    summary = customer_summary(customer_id)
    if summary is None:
        abort(404)

    for inv in summary["overdue_invoices"]:
        inv["risk"] = assess_invoice_risk(inv)
    risk = _customer_risk(summary)

    # payment record bars: positive = paid late, negative = paid early
    spread = max((abs(r["days_late"]) for r in summary["records"]), default=0) or 1
    for rec in summary["records"]:
        rec["pct"] = round(abs(rec["days_late"]) / spread * 100)

    today = my_today()
    return render_template(
        "customer_detail.html",
        s=summary,
        risk=risk,
        timeline=customer_timeline(customer_id),
        promises=customer_promises(customer_id),
        promise_stats=promise_stats(customer_id),
        promise_by_invoice={inv["id"]: latest_promise(inv["id"]) for inv in summary["open_invoices"]},
        promise_min=today.isoformat(),
        promise_max=(today + timedelta(days=PROMISE_MAX_DAYS)).isoformat(),
        promise_error=promise_error,
        error_invoice_id=error_invoice_id,
        languages=LANGUAGES,
    ), (400 if promise_error else 200)


@app.route("/customers/<int:customer_id>")
def customer_detail(customer_id):
    """One customer: money owed, why they are (or are not) risky, payment
    promises, payment record and everything the system has recorded about them."""
    body, status = _render_customer_detail(customer_id)
    return body, status


@app.route("/promise", methods=["POST"])
def add_promise():
    """FOLLOW-UP step: the customer replied "I will pay on <date>". The owner
    records it; ChaseFlow then tracks whether the promise was kept."""
    invoice_id = request.form.get("invoice_id", type=int)
    invoice = get_invoice_by_id(invoice_id) if invoice_id is not None else None
    if invoice is None or get_customer(invoice["customer_id"]) is None:
        abort(404)
    promise, error = log_promise(
        invoice_id,
        request.form.get("promised_date", ""),
        request.form.get("note", ""),
    )
    if error:
        body, status = _render_customer_detail(invoice["customer_id"], error, invoice_id)
        return body, status
    return redirect(url_for("customer_detail", customer_id=invoice["customer_id"]) + "#promises")


# --------------------------------------------------------------------------
# invoices
# --------------------------------------------------------------------------

@app.route("/invoices")
def invoices():
    """Every invoice, not just the overdue ones, with practical filters."""
    mark_overdue_invoices()
    rows = []
    for inv in sorted(INVOICES, key=lambda i: i["due_date"], reverse=True):
        overdue = is_overdue(inv)
        rows.append({
            "inv": inv,
            "overdue": overdue,
            "days_overdue": (my_today() - inv["due_date"]).days if overdue else 0,
            "undoable": can_undo_paid(inv["id"]),
        })
    counts = {
        "all": len(rows),
        "paid": sum(1 for r in rows if r["inv"]["status"] == "Paid"),
        "unpaid": sum(1 for r in rows if r["inv"]["status"] != "Paid"),
        "overdue": sum(1 for r in rows if r["overdue"]),
    }
    return render_template("invoices.html", rows=rows, counts=counts)


# --------------------------------------------------------------------------
# CSV exports
# --------------------------------------------------------------------------

@app.route("/export/invoices.csv")
def export_invoices():
    mark_overdue_invoices()
    rows = []
    for inv in sorted(INVOICES, key=lambda i: i["due_date"], reverse=True):
        overdue = is_overdue(inv)
        days = (my_today() - inv["due_date"]).days if overdue else 0
        rows.append([
            inv["invoice_no"], inv["customer_name"], f"{inv['amount']:.2f}", inv["due_date"],
            inv["status"], "yes" if overdue else "no", days,
            inv["paid_date"] or "", inv["last_reminded"] or "",
        ])
    return _csv_response(
        "chaseflow-invoices.csv",
        ["Invoice No", "Customer", "Amount (RM)", "Due Date", "Status", "Overdue",
         "Days Overdue", "Paid Date", "Last Reminded"],
        rows,
    )


@app.route("/export/activity.csv")
def export_activity():
    rows = [
        [e["timestamp"], e["customer_name"], e["invoice_no"], e["risk_tier"],
         LANGUAGES.get(e["language"], {}).get("label", ""), e["approved_by"], e["message_sent"]]
        for e in reversed(ACTIVITY_LOG)
    ]
    return _csv_response(
        "chaseflow-activity-log.csv",
        ["Time", "Customer", "Invoice No", "Risk Tier", "Language", "Approved By", "Message"],
        rows,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Debug mode (auto-reload + in-browser debugger) is only for local editing.
    # On a published Replit deployment REPLIT_DEPLOYMENT is set, so it stays off.
    is_deployed = bool(os.environ.get("REPLIT_DEPLOYMENT"))
    app.run(host="0.0.0.0", port=port, debug=not is_deployed)