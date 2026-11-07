"""I collegamenti Revolut arrivati da solede_riconciliazione: il conto delle commissioni passa da Bank Reconciliation
Settings alla Revolut Connection, e un collegamento che importava già i movimenti (prima che esistesse il flag)
continua a importarli. Dove openbanking arriva adesso (erp.solede.ch) va installata prima del deploy che la porta: la
migrate cancella i DocType rimasti senza codice, Bank Reconciliation Settings compreso, dopo le patch."""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Bank Reconciliation Settings"):
		return  # sito senza solede_riconciliazione: niente da portare
	conto = frappe.db.get_single_value("Bank Reconciliation Settings", "bank_charges_account")
	for connessione in frappe.get_all("Revolut Connection", fields=["name", "last_sync_at", "conto_commissioni"]):
		valori = {}
		if connessione.last_sync_at:
			valori["importa_movimenti"] = 1
		if conto and not connessione.conto_commissioni:
			valori.update(conto_commissioni=conto, registra_commissioni=1)
		if valori:
			frappe.db.set_value("Revolut Connection", connessione.name, valori, update_modified=False)
