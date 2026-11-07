# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta

import frappe
from frappe import _

from solede_openbanking import spese_bancarie
from solede_openbanking.api.business_registry import get_accounts, import_transactions


def sync_all_openbanking_data():
	"""
	Scheduled task che sincronizza i dati OpenBanking per tutte le company.
	Esegue:
	1. Aggiornamento dati account (get_accounts)
	2. Import transazioni degli ultimi 7 giorni (import_transactions)
	3. Registrazione delle spese bancarie riconosciute da una regola (spese_bancarie.registra)

	Esegue solo per le company che hanno business_registry_created = 1
	"""
	frappe.logger().info("Starting OpenBanking sync for all companies")

	# Ottieni tutte le settings con business registry creato
	settings_list = frappe.get_all(
		"OpenBanking Settings", filters={"business_registry_created": 1}, fields=["name", "company"]
	)

	if not settings_list:
		frappe.logger().info("No OpenBanking Settings with business registry found")
		return

	success_count = 0
	error_count = 0

	for settings in settings_list:
		company = settings.company
		try:
			sincronizza(company)
			success_count += 1
		except Exception as e:
			error_count += 1
			error_msg = str(e)
			frappe.logger().error(f"Error syncing OpenBanking data for {company}: {error_msg}")
			frappe.log_error(f"Company: {company}\nError: {error_msg}", "OpenBanking Sync Error")

	frappe.logger().info(f"OpenBanking sync completed: {success_count} success, {error_count} errors")


def sincronizza(company):
	"""Il giro di una società: dati dei conti, movimenti degli ultimi 7 giorni (arrivano anche in ritardo) e spese
	bancarie riconosciute da una regola. Lo fanno il giro orario e il pulsante «Aggiorna i movimenti» del Riepilogo
	contabile. Un movimento non importato è un errore: il dettaglio è nell'Error Log."""
	get_accounts(company)
	adesso = datetime.now()
	esito = import_transactions(company=company, from_date=(adesso - timedelta(days=7)).strftime("%Y-%m-%d"), to_date=adesso.strftime("%Y-%m-%d"))
	spese_bancarie.registra(company)
	if esito["failed"]:
		frappe.throw(_("{0} movimenti di {1} non importati da ACube: il dettaglio è nell'Error Log.").format(esito["failed"], company))
