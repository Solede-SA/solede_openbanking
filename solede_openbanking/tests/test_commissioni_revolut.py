"""Pagamento in un'altra valuta e commissione di cambio Revolut: stesso `extra.id`, due movimenti. E le spese bancarie
registrate da sole con le regole di ERPNext. Dati presi da un movimento vero (Google del 22/10/2026) con un identificativo
nuovo, sul conto Revolut di Solede SRL della copia del sito di produzione (daeok-copia.localhost). Commit patchato."""

import copy
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking import spese_bancarie
from solede_openbanking.api import business_registry
from solede_openbanking.api.business_registry import extract_unique_transaction_id, giorno_di_addebito

COMPANY = "Solede SRL"
CONTO_SPESE = "75.01.07 - Commissioni e spese bancarie - SOSRL"

PAGAMENTO = {
	"transactionId": "1922342477802212353",
	"status": "pending",
	"madeOn": "2026-10-22T00:00:00Z",
	"amount": "-108.55",
	"currencyCode": "EUR",
	"description": "Google *ads9301552188",
	"category": "uncategorized",
	"extra": {"id": "", "postingDate": "2026-10-23", "type": "CARD_PAYMENT"},
}
COMMISSIONE = {
	"transactionId": "1922342477802212354",
	"status": "pending",
	"madeOn": "2026-10-22T00:00:00Z",
	"amount": "-0.65",
	"currencyCode": "EUR",
	"description": "Fee for Google *ads9301552188",
	"category": "uncategorized",
	"extra": {"id": "", "postingDate": "2026-10-23"},
}


class TestCommissioniRevolut(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		p = patch.object(frappe.db, "commit")
		p.start()
		self.addCleanup(p.stop)
		self.conto = frappe.get_doc("OpenBanking Settings", COMPANY).accounts[0]
		self.id = str(uuid.uuid4())

	def _movimento(self, modello):
		movimento = copy.deepcopy(modello)
		movimento["extra"]["id"] = self.id
		movimento["account"] = {"uuid": self.conto.uuid}
		return movimento

	def _importa(self, *movimenti):
		risposta = {"success": True, "transactions": list(movimenti)}
		with patch.object(business_registry, "get_transactions", return_value=risposta):
			business_registry.import_transactions(COMPANY, account_uuid=self.conto.uuid)
		return {
			bt.acube_transaction_id: bt
			for bt in frappe.get_all(
				"Bank Transaction",
				filters={"acube_transaction_id": ["like", f"{self.id}%"]},
				fields=["name", "acube_transaction_id", "withdrawal", "acube_booking_date", "date", "status"],
			)
		}

	def test_chiavi(self):
		self.assertEqual(extract_unique_transaction_id(self._movimento(PAGAMENTO)), self.id)
		self.assertEqual(extract_unique_transaction_id(self._movimento(COMMISSIONE)), f"{self.id}:fee")
		bcc = {"description": "Addebito Canone home banking", "extra": {"id": self.id}}
		self.assertEqual(extract_unique_transaction_id(bcc), self.id)
		with self.assertRaises(frappe.ValidationError):
			extract_unique_transaction_id({"transactionId": "1", "extra": {}})
		self.assertEqual(giorno_di_addebito(self._movimento(PAGAMENTO)), "2026-10-23")
		with self.assertRaises(frappe.ValidationError):
			giorno_di_addebito({"transactionId": "1", "extra": {"id": "x"}})

	def test_entrambi_in_qualunque_ordine(self):
		for ordine in ((PAGAMENTO, COMMISSIONE), (COMMISSIONE, PAGAMENTO)):
			with self.subTest(primo=ordine[0]["description"]):
				self.id = str(uuid.uuid4())
				importati = self._importa(*(self._movimento(m) for m in ordine))
				self.assertEqual(importati[self.id].withdrawal, 108.55)
				self.assertEqual(importati[f"{self.id}:fee"].withdrawal, 0.65)
				self.assertEqual(str(importati[self.id].acube_booking_date), "2026-10-23")
				self.assertEqual(str(importati[self.id].date), "2026-10-22")
				# il giro dopo li riceve di nuovo: nessun doppione
				self.assertEqual(len(self._importa(*(self._movimento(m) for m in ordine))), 2)

	def _regola(self):
		frappe.get_doc({
			"doctype": "Bank Transaction Rule",
			"rule_name": f"Commissioni di cambio di prova {self.id}",
			"company": COMPANY,
			"transaction_type": "Withdrawal",
			"description_rules": [{"check": "Starts With", "value": "fee for "}],
			"classify_as": "Bank Entry",
			"bank_entry_type": "Single Account",
			"account": CONTO_SPESE,
			"priority": -1,  # prima delle regole del sito
		}).insert()

	def test_spesa_registrata_dalla_regola(self):
		self._regola()
		importati = self._importa(self._movimento(PAGAMENTO), self._movimento(COMMISSIONE))

		spese_bancarie.registra(COMPANY)

		commissione = frappe.get_doc("Bank Transaction", importati[f"{self.id}:fee"].name)
		self.assertEqual(commissione.status, "Reconciled")
		scrittura = frappe.get_doc("Journal Entry", commissione.payment_entries[0].payment_entry)
		self.assertEqual(str(scrittura.posting_date), "2026-10-23")
		righe = {r.account: (r.debit, r.credit) for r in scrittura.accounts}
		self.assertEqual(righe[CONTO_SPESE], (0.65, 0))
		self.assertEqual(righe[frappe.db.get_value("Bank Account", commissione.bank_account, "account")], (0, 0.65))
		# il pagamento non ricade nella regola: resta da abbinare
		self.assertEqual(frappe.db.get_value("Bank Transaction", importati[self.id].name, "status"), "Unreconciled")

	def test_spesa_non_registrata_non_si_riprova_ogni_ora(self):
		self._regola()
		commissione = self._importa(self._movimento(COMMISSIONE))[f"{self.id}:fee"].name
		# l'Error Log si scrive da sé, fuori dalla transazione del test: qui si guarda solo che venga chiesto
		with patch.object(spese_bancarie, "create_bank_entry_and_reconcile", side_effect=frappe.ValidationError("periodo chiuso")), \
				patch.object(frappe, "log_error") as errore:
			spese_bancarie.registra(COMPANY)
		self.assertEqual(frappe.db.get_value("Bank Transaction", commissione, ["status", "matched_transaction_rule"]), ("Unreconciled", None))
		self.assertIn(f"Spesa bancaria non registrata: {commissione}", [c.kwargs["title"] for c in errore.call_args_list])
