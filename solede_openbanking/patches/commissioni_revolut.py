"""I movimenti già importati prendono le regole nuove dell'importatore: la commissione di cambio Revolut con il suo
identificativo (prima aveva quello del pagamento, che così sarebbe tornato come doppione) e il giorno di addebito al
posto della valuta."""

import json

import frappe

from solede_openbanking.api.business_registry import extract_unique_transaction_id, giorno_di_addebito


def execute():
	for bt in frappe.get_all(
		"Bank Transaction",
		filters={"api_source": "ACube"},
		fields=["name", "acube_raw_data", "acube_transaction_log"],
	):
		movimento = json.loads(bt.acube_raw_data)
		identificativo = extract_unique_transaction_id(movimento)
		frappe.db.set_value(
			"Bank Transaction", bt.name,
			{
				"acube_transaction_id": identificativo, "transaction_id": identificativo, "reference_number": identificativo,
				"acube_booking_date": giorno_di_addebito(movimento),
			},
			update_modified=False,
		)
		frappe.db.set_value("ACube Transaction Log", bt.acube_transaction_log, "acube_transaction_id", identificativo, update_modified=False)
