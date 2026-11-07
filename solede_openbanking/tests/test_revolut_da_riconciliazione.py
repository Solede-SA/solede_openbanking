"""I collegamenti Revolut arrivati da solede_riconciliazione: conto delle commissioni e importazione già attiva passano
sulla Revolut Connection. Impostazioni di solede_riconciliazione finte; gira su daeok-copia.localhost."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking.patches import revolut_da_riconciliazione

SPESE = "75.01.07 - Commissioni e spese bancarie - SOSRL"


class TestRevolutDaRiconciliazione(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("collegamento")  # una transazione per classe: ogni test riparte senza il collegamento del precedente
		self.addCleanup(frappe.db.rollback, save_point="collegamento")

	def _collegamento(self, **valori):
		return frappe.get_doc({
			"doctype": "Revolut Connection", "bank": "Revolut Ltd", "redirect_uri": "https://erp.example.com/cb",
			"client_id": "id", "private_key": "-----BEGIN PRIVATE KEY-----\nprova\n-----END PRIVATE KEY-----",
			"importa_movimenti": 0, "registra_commissioni": 0, **valori,
		}).insert(ignore_permissions=True)

	def _patch(self, conto=SPESE):
		with patch.object(frappe.db, "exists", return_value=True), patch.object(frappe.db, "get_single_value", return_value=conto):
			revolut_da_riconciliazione.execute()

	def test_conto_e_importazione_passano_sul_collegamento(self):
		collegamento = self._collegamento(last_sync_at="2026-11-07 04:00:00")
		self._patch()
		collegamento.reload()
		self.assertEqual((collegamento.importa_movimenti, collegamento.registra_commissioni, collegamento.conto_commissioni), (1, 1, SPESE))

	def test_senza_conto_e_senza_giri_niente(self):
		collegamento = self._collegamento()
		self._patch(conto=None)
		collegamento.reload()
		self.assertEqual((collegamento.importa_movimenti, collegamento.registra_commissioni, collegamento.conto_commissioni), (0, 0, None))
