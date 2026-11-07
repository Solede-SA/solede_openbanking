"""Giro ACube di una società (orario e pulsante «Aggiorna i movimenti»): conti, movimenti, spese bancarie; un movimento
non importato è un errore. ACube finto: gira su qualunque sito con solede_openbanking."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking.api import scheduled_tasks

COMPANY = "Società di prova"


class TestSincronizza(IntegrationTestCase):
	def _sincronizza(self, falliti):
		with patch.object(scheduled_tasks, "get_accounts") as conti, \
				patch.object(scheduled_tasks, "import_transactions", return_value={"failed": falliti}) as importa, \
				patch.object(scheduled_tasks.spese_bancarie, "registra") as spese:
			try:
				scheduled_tasks.sincronizza(COMPANY)
			finally:
				conti.assert_called_once_with(COMPANY)
				self.assertEqual(importa.call_args.kwargs["company"], COMPANY)
				spese.assert_called_once_with(COMPANY)  # le spese si registrano anche se un movimento non è entrato

	def test_giro_completo(self):
		self._sincronizza(0)

	def test_movimento_non_importato_e_un_errore(self):
		with self.assertRaises(frappe.ValidationError):
			self._sincronizza(2)
