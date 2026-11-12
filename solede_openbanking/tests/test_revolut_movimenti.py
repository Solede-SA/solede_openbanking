"""Movimenti dal collegamento diretto a Revolut: la data di partenza vale sempre e la commissione di cambio compresa si
registra da sola dove il collegamento lo chiede. Revolut finto, conto Revolut di prova della società (fixtures).
Commit patchato."""

import uuid
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking import revolut_sync, spese_bancarie
from solede_openbanking.api import revolut
from solede_openbanking.tests.fixtures import COMPANY, conto_revolut


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
		self.conto = conto_revolut()
		frappe.db.set_value("Bank Account", self.conto.bank_account, "revolut_account_id", "conto-di-prova")

	def _giro(self, *movimenti, registra_commissioni=1):
		client = object.__new__(revolut.RevolutAPIClient)
		client.connection_name = "Revolut di prova"
		client._connection = frappe._dict(importa_movimenti=1, cutover_date="2026-11-07", registra_commissioni=registra_commissioni, conto_commissioni=self.conto.spese)
		with patch.object(revolut.RevolutAPIClient, "iter_transactions", return_value=list(movimenti)):
			return revolut_sync._pull_transactions(client, None, None)

	def _bt(self, movimento):
		return frappe.get_doc("Bank Transaction", {"transaction_id": movimento["id"], "bank_account": self.conto.bank_account})

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
		self.assertEqual({r.account: r.debit for r in scrittura.accounts}[self.conto.spese], 0.65)
		self._giro(pagamento)  # il giro dopo lo rilegge: nessun doppione
		self.assertEqual(frappe.db.count("Bank Transaction", {"transaction_id": pagamento["id"]}), 1)

	def _in_sospeso(self, importo):
		"""Un pagamento con carta che Revolut non ha ancora completato."""
		addebito = {**_movimento("2026-11-12", importo), "state": "pending", "created_at": "2026-11-12T12:36:53Z"}
		del addebito["completed_at"]
		return addebito

	def test_in_sospeso_entra_e_poi_si_completa(self):
		addebito = self._in_sospeso(2.03)
		self.assertEqual(self._giro(addebito)["created"], 1)
		bt = self._bt(addebito)
		self.assertEqual((bt.revolut_in_sospeso, str(bt.date), bt.revolut_completed_at, bt.withdrawal), (1, "2026-11-12", None, 2.03))
		self.assertEqual(self._giro(addebito)["mismatches"], [])  # riletto ancora in sospeso: niente cambia
		esito = self._giro({**addebito, "state": "completed", "completed_at": "2026-11-14T09:00:00Z"})
		self.assertEqual((esito["created"], esito["updated"], esito["mismatches"]), (0, 1, []))
		bt = self._bt(addebito)
		# il giorno diventa quello di completamento, con il saldo di Revolut
		self.assertEqual((bt.revolut_in_sospeso, str(bt.date), str(bt.revolut_completed_at), bt.revolut_balance_after), (0, "2026-11-14", "2026-11-14 09:00:00", 1000))

	def test_annullato_da_revolut(self):
		libero, abbinato = self._in_sospeso(2.03), self._in_sospeso(5.0)
		self._giro(libero, abbinato)
		# il secondo è già registrato, come farebbe una regola dei movimenti
		spese_bancarie._registra(self._bt(abbinato), frappe._dict(classify_as="Bank Entry", account=self.conto.spese))
		annullati = ({**libero, "state": "reverted"}, {**abbinato, "state": "declined"})
		# l'Error Log si scrive da sé, fuori dalla transazione del test: qui si guarda solo che venga chiesto
		with patch.object(frappe, "log_error") as errore:
			esito = self._giro(*annullati)
			self._giro(*annullati)  # il giro lo rilegge per giorni: si dice una volta sola
		self.assertEqual(self._bt(libero).docstatus, 2)  # mai avvenuto e non abbinato: annullato anche qui
		registrato = self._bt(abbinato)
		self.assertEqual((registrato.docstatus, registrato.status), (1, "Reconciled"))  # abbinato: non si disfa niente
		[differenza] = esito["mismatches"]
		self.assertEqual((differenza["bank_transaction"], differenza["differences"]["state"][1]), (registrato.name, "declined"))
		self.assertIn(registrato.payment_entries[0].payment_entry, differenza["differences"]["state"][0])
		self.assertEqual([c.kwargs["title"] for c in errore.call_args_list], [f"Revolut ha annullato un movimento già abbinato: {registrato.name}"])
		self.assertEqual(frappe.db.count("Comment", {"reference_doctype": "Bank Transaction", "reference_name": registrato.name, "content": ["like", f"%{revolut_sync.ANNULLATO}%"]}), 1)

	def test_dopo_il_giro_le_regole_della_societa(self):
		collegamento = MagicMock(cutover_date="2026-11-07", last_sync_at=None)
		with patch.object(revolut_sync.frappe, "get_doc", return_value=collegamento), patch.object(revolut_sync, "RevolutAPIClient"), \
				patch.object(revolut_sync, "_pull_transactions", return_value={}), patch.object(revolut_sync.spese_bancarie, "registra") as registra:
			revolut_sync._sync_one_connection("Revolut di prova")
		registra.assert_any_call(COMPANY)

	def test_senza_il_campo_la_commissione_resta_li(self):
		pagamento = _movimento("2026-11-07", 108.55, 0.65)
		self._giro(pagamento, registra_commissioni=0)
		self.assertEqual((self._bt(pagamento).unallocated_amount, len(self._bt(pagamento).payment_entries)), (109.2, 0))

	def test_saldo_dal_conto_mappato(self):
		with patch.object(revolut, "RevolutAPIClient") as client:
			client.return_value.get_accounts.return_value = [{"id": "altro", "balance": 1}, {"id": "conto-di-prova", "balance": 58082.53}]
			self.assertEqual(revolut.saldo(self.conto.bank_account), 58082.53)
			client.assert_called_once_with(frappe.db.get_value("Bank Account", self.conto.bank_account, "bank"))
