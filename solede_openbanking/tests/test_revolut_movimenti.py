"""Movimenti dal collegamento diretto a Revolut: la data di partenza vale sempre e la commissione di cambio compresa si
registra da sola dove il collegamento lo chiede. Revolut finto, conto Revolut vero di Solede SRL della copia del sito
di produzione (daeok-copia.localhost). Commit patchato."""

import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking import revolut_sync
from solede_openbanking.api import revolut

CONTO = "Revolut EUR - Solede SRL - Revolut Ltd"
SPESE = "75.01.07 - Commissioni e spese bancarie - SOSRL"


def _movimento(giorno, importo, commissione=0.0):
	return {
		"id": str(uuid.uuid4()), "state": "completed", "type": "card_payment", "completed_at": f"{giorno}T15:00:00Z",
		"legs": [{"account_id": "conto-di-prova", "amount": -importo, "fee": commissione, "currency": "EUR", "description": "Google", "balance": 1000}],
	}


class TestMovimentiRevolut(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		p = patch.object(frappe.db, "commit")
		p.start()
		self.addCleanup(p.stop)
		frappe.db.set_value("Bank Account", CONTO, "revolut_account_id", "conto-di-prova")

	def _giro(self, *movimenti, registra_commissioni=1):
		client = object.__new__(revolut.RevolutAPIClient)
		client.connection_name = "Revolut di prova"
		client._connection = frappe._dict(importa_movimenti=1, cutover_date="2026-11-07", registra_commissioni=registra_commissioni, conto_commissioni=SPESE)
		with patch.object(revolut.RevolutAPIClient, "iter_transactions", return_value=list(movimenti)):
			return revolut_sync._pull_transactions(client, None, None)

	def _bt(self, movimento):
		return frappe.get_doc("Bank Transaction", {"transaction_id": movimento["id"], "bank_account": CONTO})

	def test_prima_della_partenza_non_entra(self):
		vecchio = _movimento("2026-11-01", 62.78)
		self.assertEqual(self._giro(vecchio)["created"], 0)
		self.assertFalse(frappe.db.exists("Bank Transaction", {"transaction_id": vecchio["id"]}))

	def test_la_commissione_compresa_diventa_spesa_bancaria(self):
		pagamento = _movimento("2026-11-07", 108.55, 0.65)
		self.assertEqual(self._giro(pagamento)["created"], 1)
		bt = self._bt(pagamento)
		self.assertEqual((bt.withdrawal, bt.included_fee, bt.unallocated_amount), (109.2, 0.65, 108.55))  # resta il netto da abbinare
		scrittura = frappe.get_doc("Journal Entry", bt.payment_entries[0].payment_entry)
		self.assertEqual({r.account: r.debit for r in scrittura.accounts}[SPESE], 0.65)
		self._giro(pagamento)  # il giro dopo lo rilegge: nessun doppione
		self.assertEqual(frappe.db.count("Bank Transaction", {"transaction_id": pagamento["id"]}), 1)

	def test_senza_il_campo_la_commissione_resta_li(self):
		pagamento = _movimento("2026-11-07", 108.55, 0.65)
		self._giro(pagamento, registra_commissioni=0)
		self.assertEqual((self._bt(pagamento).unallocated_amount, len(self._bt(pagamento).payment_entries)), (109.2, 0))

	def test_saldo_dal_conto_mappato(self):
		with patch.object(revolut, "RevolutAPIClient") as client:
			client.return_value.get_accounts.return_value = [{"id": "altro", "balance": 1}, {"id": "conto-di-prova", "balance": 58082.53}]
			self.assertEqual(revolut.saldo(CONTO), 58082.53)
			client.assert_called_once_with(frappe.db.get_value("Bank Account", CONTO, "bank"))
