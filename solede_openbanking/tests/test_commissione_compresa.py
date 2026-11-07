"""Commissione Revolut compresa nell'importo: spesa bancaria a parte, il movimento resta da abbinare per il netto. Conti
veri di Solede SRL della copia del sito di produzione (daeok-copia.localhost); tutto resta nella transazione del test."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from solede_openbanking.spese_bancarie import registra_commissione_compresa

CONTO = "Revolut EUR - Solede SRL - Revolut Ltd"
SPESE = "75.01.07 - Commissioni e spese bancarie - SOSRL"


def _movimento(uscita, commissione):
	return frappe.get_doc({
		"doctype": "Bank Transaction", "date": today(), "bank_account": CONTO, "company": "Solede SRL", "currency": "EUR",
		"withdrawal": uscita, "included_fee": commissione, "description": "Anthropic - [card_payment]",
		"transaction_id": frappe.generate_hash(length=12),
	}).insert().submit()


class TestCommissioneCompresa(IntegrationTestCase):
	def test_commissione_a_spese_bancarie_e_netto_da_abbinare(self):
		bt = _movimento(40.06, 0.40)
		scrittura = registra_commissione_compresa(bt, SPESE)
		righe = {r.account: r for r in scrittura.accounts}
		banca = frappe.db.get_value("Bank Account", CONTO, "account")
		self.assertEqual((righe[SPESE].debit_in_account_currency, righe[banca].credit_in_account_currency, scrittura.docstatus), (0.40, 0.40, 1))
		bt.reload()
		self.assertEqual((bt.unallocated_amount, bt.status), (39.66, "Unreconciled"))
		self.assertIsNone(registra_commissione_compresa(bt, SPESE))  # una volta sola

	def test_senza_commissione_niente(self):
		bt = _movimento(9.0, 0)
		self.assertIsNone(registra_commissione_compresa(bt, SPESE))
		bt.reload()
		self.assertEqual((bt.unallocated_amount, bt.payment_entries), (9.0, []))
