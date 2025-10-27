# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta

import frappe
from frappe import _

from solede_openbanking.api.business_registry import get_accounts, import_transactions


def sync_all_openbanking_data():
	"""
	Scheduled task che sincronizza i dati OpenBanking per tutte le company.
	Esegue:
	1. Aggiornamento dati account (get_accounts)
	2. Import transazioni degli ultimi 7 giorni (import_transactions)

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
		frappe.logger().info(f"Syncing OpenBanking data for company: {company}")

		try:
			# 1. Aggiorna i dati degli account
			frappe.logger().info(f"Updating accounts for {company}")
			accounts_result = get_accounts(company)

			if accounts_result.get("success"):
				frappe.logger().info(f"Updated {accounts_result.get('count', 0)} accounts for {company}")

			# 2. Importa le transazioni degli ultimi 7 giorni
			to_date = datetime.now().strftime("%Y-%m-%d")
			from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

			frappe.logger().info(f"Importing transactions for {company} from {from_date} to {to_date}")
			import_result = import_transactions(company=company, from_date=from_date, to_date=to_date)

			if import_result.get("success"):
				frappe.logger().info(
					f"Imported {import_result.get('imported', 0)} transactions for {company} "
					f"(skipped: {import_result.get('skipped', 0)}, failed: {import_result.get('failed', 0)})"
				)

			success_count += 1

		except Exception as e:
			error_count += 1
			error_msg = str(e)
			frappe.logger().error(f"Error syncing OpenBanking data for {company}: {error_msg}")
			frappe.log_error(f"Company: {company}\nError: {error_msg}", "OpenBanking Sync Error")
			continue

	frappe.logger().info(f"OpenBanking sync completed: {success_count} success, {error_count} errors")
