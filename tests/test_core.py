"""Tests for the rules that do not need the AI: risk tiers, payment promises,
mark-paid / undo, reset, the AI prompt, and the no-key fallback.

Run:  python -m unittest discover tests
"""
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

os.environ.pop("GEMINI_API_KEY", None)  # tests must never call the real API

import data  # noqa: E402
import reminder_ai  # noqa: E402


class RiskRules(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(reminder_ai.explain_risk(3, 0)["risk_tier"], "low")
        self.assertEqual(reminder_ai.explain_risk(10, 0)["risk_tier"], "medium")
        self.assertEqual(reminder_ai.explain_risk(3, 2)["risk_tier"], "medium")
        self.assertEqual(reminder_ai.explain_risk(20, 0)["risk_tier"], "medium")
        self.assertEqual(reminder_ai.explain_risk(20, 2)["risk_tier"], "high")


class PromiseTracking(unittest.TestCase):
    def setUp(self):
        data.reset_demo_data()

    def test_seed_statuses(self):
        self.assertEqual(data.latest_promise(2)["status"], "broken")
        self.assertEqual(data.latest_promise(4)["status"], "pending")

    def test_log_promise_validation(self):
        today = data.my_today()
        self.assertIsNotNone(data.log_promise(5, today.isoformat())[0])
        self.assertIsNotNone(data.log_promise(1, (today + timedelta(days=60)).isoformat())[0])
        for bad in ((1, (today - timedelta(days=1)).isoformat()),   # in the past
                    (1, (today + timedelta(days=61)).isoformat()),  # too far away
                    (1, "not-a-date"),
                    (6, today.isoformat()),                          # invoice already paid
                    (999, today.isoformat())):                       # no such invoice
            promise, error = data.log_promise(*bad)
            self.assertIsNone(promise)
            self.assertTrue(error)

    def test_note_is_trimmed(self):
        promise, _ = data.log_promise(5, data.my_today().isoformat(), "x" * 500)
        self.assertEqual(len(promise["note"]), data.PROMISE_NOTE_MAX)

    def test_newer_promise_replaces_older(self):
        later = (data.my_today() + timedelta(days=5)).isoformat()
        data.log_promise(4, later)
        statuses = [p["status"] for p in data.promises_for_invoice(4)]
        self.assertEqual(statuses, ["pending", "replaced"])

    def test_paid_on_time_is_kept_and_undo_restores(self):
        self.assertTrue(data.mark_paid(4))
        self.assertEqual(data.latest_promise(4)["status"], "kept")
        self.assertTrue(data.mark_unpaid(4))
        self.assertEqual(data.latest_promise(4)["status"], "pending")

    def test_paid_after_promised_date_is_paid_late(self):
        data.mark_paid(2)  # promised 2 days ago, paid today
        self.assertEqual(data.latest_promise(2)["status"], "paid_late")

    def test_context_for_ai(self):
        context = data.promise_context(data.get_invoice_by_id(2))
        self.assertIn("promised to pay on", context["ai_text"])
        self.assertIn("Broken promise", context["hint"])
        self.assertIsNone(data.promise_context(data.get_invoice_by_id(1)))

    def test_reset_restores_seed_promises(self):
        data.log_promise(5, data.my_today().isoformat())
        data.reset_demo_data()
        self.assertEqual(len(data.PROMISES), 2)


class UndoPaid(unittest.TestCase):
    def setUp(self):
        data.reset_demo_data()

    def test_only_this_runs_payments_can_be_undone(self):
        self.assertFalse(data.mark_unpaid(7))  # paid history that came with the demo data
        data.mark_paid(1)
        self.assertTrue(data.can_undo_paid(1))
        self.assertTrue(data.mark_unpaid(1))
        self.assertEqual(data.get_invoice_by_id(1)["status"], "Unpaid")


class AiLayer(unittest.TestCase):
    def setUp(self):
        data.reset_demo_data()
        data.mark_overdue_invoices()

    def test_prompt_includes_promise_only_when_given(self):
        invoice = dict(data.get_invoice_by_id(2))
        plain = reminder_ai._build_prompt(invoice, "medium", "en")
        self.assertNotIn("Payment promise", plain)
        invoice["promise_context"] = "The customer promised to pay on 19 Oct 2026."
        with_promise = reminder_ai._build_prompt(invoice, "medium", "en")
        self.assertIn("Payment promise: The customer promised to pay on 19 Oct 2026.", with_promise)

    def test_cache_key_changes_with_promise(self):
        invoice = dict(data.get_invoice_by_id(2))
        first = reminder_ai._cache_key(invoice, "en")
        invoice["promise_context"] = "something"
        self.assertNotEqual(first, reminder_ai._cache_key(invoice, "en"))

    def test_fallback_when_no_api_key(self):
        invoice = data.get_invoice_by_id(2)
        for code in reminder_ai.LANGUAGES:
            draft = reminder_ai.generate_reminder_draft(dict(invoice), code, prefetch_others=False)
            self.assertEqual(draft["source"], "rules")
            self.assertIn(invoice["invoice_no"], draft["message"])


if __name__ == "__main__":
    unittest.main()