"""Normalizzazione delle transazioni Revolut Business API (nessun accesso al DB).

Casi emersi dagli estratti CHF giugno–settembre 2026: commissione di cambio compresa
nel withdrawal (semantica ERPNext `included_fee` e «Total amount» del CSV), carte
«pending» scartate, verifiche carta a zero ignorate, cambio tra conti propri con
una voce per leg.
"""

import frappe
from frappe.tests import IntegrationTestCase

from solede_openbanking.api.revolut import normalize_revolut_api_tx
from solede_openbanking.revolut_sync import _backfill_updates, _differences

CHF_ACCOUNT = "aadeef7a-chf"
EUR_ACCOUNT = "dc4fd92c-eur"


def _tx(state="completed", tx_type="card_payment", legs=None):
	return {
		"id": "6a5b615f-fb2c-adf4-a273-b4fe2e0eaf66",
		"type": tx_type,
		"state": state,
		"created_at": "2026-07-19T01:03:04.123Z",
		"completed_at": "2026-07-19T01:03:04.123Z",
		"merchant": {"name": "Anthropic"},
		"legs": legs if legs is not None else [_card_leg()],
	}


def _card_leg(amount=-39.66, fee=0.40):
	return {
		"leg_id": "leg-1",
		"account_id": CHF_ACCOUNT,
		"amount": amount,
		"fee": fee,
		"currency": "CHF",
		"bill_amount": -49.03,
		"bill_currency": "USD",
		"balance": 1866.29,
		"description": "Anthropic",
	}


class TestNormalizeRevolutApiTx(IntegrationTestCase):
	def test_commissione_compresa_nel_withdrawal(self):
		(entry,) = normalize_revolut_api_tx(_tx())
		self.assertAlmostEqual(entry["withdrawal"], 40.06, places=2)
		self.assertEqual(entry["deposit"], 0.0)
		self.assertAlmostEqual(entry["included_fee"], 0.40, places=2)
		self.assertEqual(entry["date"], "2026-07-19")
		self.assertEqual(entry["revolut_completed_at"], "2026-07-19 01:03:04")
		self.assertEqual(entry["solede_orig_currency"], "USD")
		self.assertAlmostEqual(entry["solede_orig_amount"], 49.03, places=2)
		self.assertEqual(entry["revolut_balance_after"], 1866.29)
		self.assertEqual(entry["_account_id"], CHF_ACCOUNT)
		self.assertEqual(entry["description"], "Anthropic - [card_payment]")

	def test_pending_non_importata(self):
		self.assertEqual(normalize_revolut_api_tx(_tx(state="pending")), [])

	def test_verifica_carta_a_zero_ignorata(self):
		self.assertEqual(normalize_revolut_api_tx(_tx(legs=[_card_leg(amount=0, fee=0)])), [])

	def test_deposito_con_commissione_accredita_il_netto(self):
		(entry,) = normalize_revolut_api_tx(_tx(tx_type="transfer", legs=[_card_leg(amount=100.0, fee=1.0)]))
		self.assertAlmostEqual(entry["deposit"], 99.0, places=2)
		self.assertEqual(entry["withdrawal"], 0.0)
		self.assertAlmostEqual(entry["included_fee"], 1.0, places=2)

	def test_cambio_tra_conti_propri_una_voce_per_leg(self):
		legs = [
			{"leg_id": "leg-eur", "account_id": EUR_ACCOUNT, "amount": -1.30, "fee": 0, "currency": "EUR", "balance": 0.0,
			 "description": "Exchanged to CHF Main"},
			{"leg_id": "leg-chf", "account_id": CHF_ACCOUNT, "amount": 1.19, "fee": 0, "currency": "CHF", "balance": -5.92,
			 "description": "Exchanged from EUR Main"},
		]
		eur, chf = normalize_revolut_api_tx(_tx(tx_type="exchange", legs=legs))
		self.assertEqual(eur["transaction_id"], chf["transaction_id"])
		self.assertEqual((eur["_account_id"], eur["withdrawal"], eur["deposit"], eur["currency"]), (EUR_ACCOUNT, 1.30, 0.0, "EUR"))
		self.assertEqual((chf["_account_id"], chf["withdrawal"], chf["deposit"], chf["currency"]), (CHF_ACCOUNT, 0.0, 1.19, "CHF"))
		self.assertEqual(chf["revolut_balance_after"], -5.92)


def _acube_row(**overrides):
	"""Bank Transaction importata da ACube: senza saldo, completamento e tipo Revolut."""
	return frappe._dict(
		{
			"name": "ACC-BTN-2026-00700",
			"date": "2026-07-19",
			"deposit": 0.0,
			"withdrawal": 40.06,
			"included_fee": 0.40,
			"revolut_balance_after": 0.0,
			"revolut_completed_at": None,
			"transaction_type": None,
			**overrides,
		}
	)


class TestRigaGiaImportata(IntegrationTestCase):
	"""Riga già in ERPNext (ACube su CB Medical, CSV su Solede SA) ritrovata dal sync Revolut."""

	def setUp(self):
		(self.entry,) = normalize_revolut_api_tx(_tx())

	def test_riempie_saldo_completamento_e_tipo_mancanti(self):
		self.assertEqual(
			_backfill_updates(_acube_row(), self.entry),
			{
				"revolut_balance_after": 1866.29,
				"revolut_completed_at": "2026-07-19 01:03:04",
				"transaction_type": "card_payment",
			},
		)

	def test_non_sovrascrive_i_campi_gia_presenti(self):
		row = _acube_row(
			revolut_balance_after=10.0,
			revolut_completed_at="2026-07-19 01:03:04",
			transaction_type="topup",
		)
		self.assertEqual(_backfill_updates(row, self.entry), {})

	def test_riga_uguale_nessuna_differenza(self):
		self.assertEqual(_differences(_acube_row(), self.entry), {})

	def test_importo_senza_commissione_e_data_di_inizio(self):
		row = _acube_row(date="2026-07-18", withdrawal=39.66, included_fee=0.0)
		self.assertEqual(
			_differences(row, self.entry),
			{
				"date": ("2026-07-18", "2026-07-19"),
				"withdrawal": (39.66, 40.06),
				"included_fee": (0.0, 0.40),
			},
		)

