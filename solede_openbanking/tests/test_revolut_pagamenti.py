"""Collegamento Revolut per i bonifici: le chiamate all'interfaccia (verifica del nome, controparte, bozza), il consenso
con i permessi del collegamento e il giro notturno che salta i collegamenti senza movimenti. HTTP finto."""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking import revolut_sync
from solede_openbanking.api import revolut

IBAN = "IT60X0542811101000000123456"


def _client():
	client = object.__new__(revolut.RevolutAPIClient)  # senza Revolut Connection: qui conta solo cosa si spedisce
	client.connection_name = "Revolut di prova"
	client._endpoints = revolut._endpoints("Production")
	client._access_token = "token"
	return client


def _risposta(dati, stato=200):
	return MagicMock(status_code=stato, content=b"x" if dati is not None else b"", json=MagicMock(return_value=dati))


class TestClientPagamenti(IntegrationTestCase):
	def test_verifica_del_nome_europea(self):
		with patch.object(revolut.requests, "request", return_value=_risposta({"result_code": "matched"})) as chiamata:
			self.assertEqual(_client().verifica_nome(IBAN, "GLS ENTERPRISE SRL")["result_code"], "matched")
		metodo, url = chiamata.call_args.args
		self.assertEqual((metodo, url.endswith("/account-name-validation")), ("POST", True))
		self.assertEqual(chiamata.call_args.kwargs["json"], {"iban": IBAN, "recipient_country": "IT", "recipient_currency": "EUR", "company_name": "GLS ENTERPRISE SRL"})

	def test_controparte_gia_nota(self):
		esistenti = [{"id": "c1", "accounts": [{"id": "a1", "iban": IBAN}]}]
		with patch.object(revolut.requests, "request", return_value=_risposta(esistenti)) as chiamata:
			self.assertEqual(_client().controparte(IBAN, "GLS ENTERPRISE SRL"), ("c1", "a1"))
		self.assertEqual((chiamata.call_count, chiamata.call_args.kwargs["params"]), (1, {"iban": IBAN}))  # cercata per IBAN, nessuna nuova

	def test_controparte_nuova(self):
		risposte = [_risposta([]), _risposta({"id": "c2", "accounts": [{"id": "a2"}]})]
		with patch.object(revolut.requests, "request", side_effect=risposte) as chiamata:
			self.assertEqual(_client().controparte(IBAN, "GLS ENTERPRISE SRL"), ("c2", "a2"))
		self.assertEqual(chiamata.call_args.kwargs["json"], {"company_name": "GLS ENTERPRISE SRL", "bank_country": "IT", "currency": "EUR", "iban": IBAN})

	def test_bozza_cancellata_senza_contenuto(self):
		with patch.object(revolut.requests, "request", return_value=_risposta(None, 204)) as chiamata:
			self.assertIsNone(_client().elimina_bozza("bozza-1"))
		self.assertEqual(chiamata.call_args.args[0], "DELETE")

	def test_bozze_da_approvare(self):
		with patch.object(revolut.requests, "request", return_value=_risposta({"payment_orders": [{"id": "b1", "title": "Bonifico"}]})) as chiamata:
			self.assertEqual(_client().bozze(), [{"id": "b1", "title": "Bonifico"}])
		self.assertEqual(chiamata.call_args.args, ("GET", "https://b2b.revolut.com/api/1.0/payment-drafts"))

	def test_errore_di_revolut_si_vede(self):
		with patch.object(revolut.requests, "request", return_value=_risposta({"message": "no"}, 400)), self.assertRaises(revolut.RevolutAPIError):
			_client().crea_bozza("Titolo", "conto", ("c1", "a1"), 10.0, "Fattura 1")


class TestCollegamento(IntegrationTestCase):
	def test_il_consenso_chiede_i_permessi_del_collegamento(self):
		collegamento = frappe._dict(name="Revolut di prova", client_id="id", redirect_uri="https://erp.example.com/cb", environment="Production", permessi="READ,WRITE")
		url = revolut.build_revolut_consent_url(collegamento)
		self.assertEqual(parse_qs(urlparse(url).query)["scope"], ["READ,WRITE"])

	def test_il_giro_salta_chi_non_importa_movimenti(self):
		with patch.object(frappe, "get_all", return_value=[]) as elenco:
			revolut_sync.sync_revolut_transactions()
		self.assertEqual(elenco.call_args.kwargs["filters"]["importa_movimenti"], 1)
