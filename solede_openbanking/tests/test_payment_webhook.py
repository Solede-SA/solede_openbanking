"""Test del routing del webhook payment: la Payment Entry nasce sul webhook "submitted".

"submitted" e' l'unico webhook di successo che A-Cube invia per i bonifici
outbound (lo stato non viene mai piu' aggiornato dopo la sottomissione alla
banca): il test blinda la condizione contro regressioni verso stati mai
inviati (confirmed/completed). create_payment_entry_from_payment e' mockata:
qui si testa il routing, non la contabilita'. Commit patchato (anti
avvelenamento del sito).
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking.api import webhooks


class TestPaymentWebhookRouting(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		p = patch.object(frappe.db, "commit")
		p.start()
		self.addCleanup(p.stop)
		self.company = frappe.db.get_value("Company", {}, "name")
		# PI reale del sito: il save() dentro il handler ri-valida i Link.
		# La contabilita' resta mockata, la fattura non viene toccata.
		self.purchase_invoice = frappe.db.get_value("Purchase Invoice", {}, "name")
		self.assertTrue(self.purchase_invoice, "Serve almeno una Purchase Invoice sul sito di test")

	def _make_payment(self, uuid):
		doc = frappe.get_doc({
			"doctype": "OpenBanking Payment",
			"uuid": uuid,
			"payment_direction": "outbound",
			"status": "pending",
			"system": "sepa",
			"amount": 100,
			"currency_code": "EUR",
			"company": self.company,
			"reference_doctype": "Purchase Invoice",
			"reference_name": self.purchase_invoice,
		})
		doc.insert(ignore_permissions=True)
		return doc

	def _payload(self, uuid, status, **top_level_extra):
		return {
			"fiscalId": "_TEST",
			"payment": {
				"uuid": uuid,
				"direction": "outbound",
				"status": status,
				"amount": "100.00",
				"currencyCode": "EUR",
				"endToEndId": "_TEST-E2E",
			},
			**top_level_extra,
		}

	def test_submitted_creates_payment_entry(self):
		payment = self._make_payment("test-routing-submitted")
		with patch.object(webhooks, "create_payment_entry_from_payment") as create_pe:
			webhooks.handle_payment_webhook(
				self._payload("test-routing-submitted", "submitted"), self.company, None
			)
		create_pe.assert_called_once()
		self.assertEqual(create_pe.call_args.args[0].name, payment.name)
		payment.reload()
		self.assertEqual(payment.status, "submitted")

	def test_failed_does_not_create_payment_entry(self):
		payment = self._make_payment("test-routing-failed")
		with patch.object(webhooks, "create_payment_entry_from_payment") as create_pe:
			webhooks.handle_payment_webhook(
				self._payload(
					"test-routing-failed", "failed",
					errorClass="InsufficientFunds", errorMessage="boom",
				),
				self.company, None,
			)
		create_pe.assert_not_called()
		payment.reload()
		self.assertEqual(payment.status, "failed")
		self.assertIn("InsufficientFunds", payment.error_message)
