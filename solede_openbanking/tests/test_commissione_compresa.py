"""Commissione Revolut compresa nell'importo: spesa bancaria a parte, il movimento resta da abbinare per il netto. Conto
Revolut e conto spese di prova (fixtures); tutto resta nella transazione del test."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from solede_openbanking.spese_bancarie import registra_commissione_compresa
from solede_openbanking.tests.fixtures import COMPANY, conto_revolut


def _movimento(conto, uscita, commissione):
	return frappe.get_doc({
		"doctype": "Bank Transaction", "date": today(), "bank_account": conto.bank_account, "company": COMPANY, "currency": "EUR",
		"withdrawal": uscita, "included_fee": commissione, "description": "Anthropic - [card_payment]",
		"transaction_id": frappe.generate_hash(length=12),
	}).insert().submit()


class TestCommissioneCompresa(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.conto = conto_revolut()

	def test_commissione_a_spese_bancarie_e_netto_da_abbinare(self):
		bt = _movimento(self.conto, 40.06, 0.40)
		scrittura = registra_commissione_compresa(bt, self.conto.spese)
		righe = {r.account: r for r in scrittura.accounts}
		self.assertEqual((righe[self.conto.spese].debit_in_account_currency, righe[self.conto.account].credit_in_account_currency, scrittura.docstatus), (0.40, 0.40, 1))
		bt.reload()
		self.assertEqual((bt.unallocated_amount, bt.status), (39.66, "Unreconciled"))
		self.assertIsNone(registra_commissione_compresa(bt, self.conto.spese))  # una volta sola

	def test_senza_commissione_niente(self):
		bt = _movimento(self.conto, 9.0, 0)
		self.assertIsNone(registra_commissione_compresa(bt, self.conto.spese))
		bt.reload()
		self.assertEqual((bt.unallocated_amount, bt.payment_entries), (9.0, []))
