"""Il registro ACube aggiungeva una copia di ogni movimento a ogni importazione oraria, anche identica: restano solo le
copie con una versione del movimento (stato, importo, codice ACube) che il registro non aveva ancora, la stessa regola
dell'importazione. Nei registri dove pagamento e commissione Revolut erano mescolati le versioni si alternavano: per
questo si guarda a tutte, non solo alla precedente."""

import json

import frappe

from solede_openbanking.api.business_registry import versione

RICEZIONE = "ACube Transaction Reception"


def execute():
	for log in frappe.get_all("ACube Transaction Log", fields=["name", "raw_data"]):
		viste = {versione(json.loads(log.raw_data))}
		doppie = []
		for ricezione in frappe.get_all(
			RICEZIONE, filters={"parent": log.name, "parenttype": "ACube Transaction Log"}, fields=["name", "raw_data"], order_by="idx asc"
		):
			attuale = versione(json.loads(ricezione.raw_data))
			if attuale in viste:
				doppie.append(ricezione.name)
			else:
				viste.add(attuale)
		if doppie:
			frappe.db.delete(RICEZIONE, {"name": ["in", doppie]})
