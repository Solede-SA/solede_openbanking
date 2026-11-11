"""I collegamenti Revolut arrivati da solede_riconciliazione: conto delle commissioni e importazione già attiva passano
sulla Revolut Connection. Impostazioni di solede_riconciliazione finte, banca e conto spese di prova (fixtures)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking.patches import revolut_da_riconciliazione
from solede_openbanking.tests.fixtures import BANCA, conto_revolut


class TestRevolutDaRiconciliazione(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("collegamento")  # una transazione per classe: ogni test riparte senza il collegamento del precedente
		self.addCleanup(frappe.db.rollback, save_point="collegamento")
		self.spese = conto_revolut().spese

	def _collegamento(self, **valori):
		return frappe.get_doc({
			"doctype": "Revolut Connection", "bank": BANCA, "redirect_uri": "https://erp.example.com/cb",
			"client_id": "id", "private_key": "-----BEGIN PRIVATE KEY-----\nprova\n-----END PRIVATE KEY-----",
			"importa_movimenti": 0, "registra_commissioni": 0, **valori,
		}).insert(ignore_permissions=True)

	def _patch(self, conto):
		with patch.object(frappe.db, "exists", return_value=True), patch.object(frappe.db, "get_single_value", return_value=conto):
			revolut_da_riconciliazione.execute()

	def test_conto_e_importazione_passano_sul_collegamento(self):
		collegamento = self._collegamento(last_sync_at="2026-11-07 04:00:00")
		self._patch(self.spese)
		collegamento.reload()
		self.assertEqual((collegamento.importa_movimenti, collegamento.registra_commissioni, collegamento.conto_commissioni), (1, 1, self.spese))

	def test_senza_conto_e_senza_giri_niente(self):
		collegamento = self._collegamento()
		self._patch(conto=None)
		collegamento.reload()
		self.assertEqual((collegamento.importa_movimenti, collegamento.registra_commissioni, collegamento.conto_commissioni), (0, 0, None))
