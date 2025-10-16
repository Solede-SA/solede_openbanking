# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _


@frappe.whitelist()
def inspect_account_raw_data(company, account_uuid):
	"""
	Ispeziona il raw_data di un account OpenBanking per debug.

	Args:
		company: Nome della company
		account_uuid: UUID dell'account

	Returns:
		dict: Raw data formattato
	"""
	if not frappe.db.exists("OpenBanking Settings", company):
		frappe.throw(_("OpenBanking Settings not found for company: {0}").format(company))

	settings = frappe.get_doc("OpenBanking Settings", company)

	for acc in settings.accounts:
		if acc.uuid == account_uuid:
			if acc.raw_data:
				try:
					raw_data = json.loads(acc.raw_data)
					return {
						"success": True,
						"uuid": acc.uuid,
						"iban": acc.iban,
						"bank_display": acc.bank_display,
						"raw_data": raw_data,
						"raw_data_json": json.dumps(raw_data, indent=2)
					}
				except json.JSONDecodeError as e:
					return {
						"success": False,
						"error": f"JSON decode error: {str(e)}",
						"raw_data_string": acc.raw_data
					}
			else:
				return {
					"success": False,
					"error": "No raw_data found for this account"
				}

	return {
		"success": False,
		"error": f"Account not found: {account_uuid}"
	}
