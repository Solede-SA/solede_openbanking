import frappe
import json
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 200
		},
		{
			"fieldname": "iban",
			"label": _("IBAN"),
			"fieldtype": "Data",
			"width": 200
		},
		{
			"fieldname": "bank_display",
			"label": _("Bank"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "balance_display",
			"label": _("Balance"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "consent_expires_display",
			"label": _("Consent Expires"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "enabled",
			"label": _("Enabled"),
			"fieldtype": "Check",
			"width": 80
		},
		{
			"fieldname": "uuid",
			"label": _("UUID"),
			"fieldtype": "Data",
			"width": 100
		}
	]


def get_data(filters):
	data = []

	settings_list = frappe.get_all(
		"OpenBanking Settings",
		fields=["name", "company"]
	)

	for settings in settings_list:
		accounts = frappe.get_all(
			"OpenBanking Account",
			filters={"parent": settings.name, "parenttype": "OpenBanking Settings"},
			fields=["iban", "bank_display", "balance_display", "consent_expires_display", "enabled", "uuid", "raw_data"]
		)

		for account in accounts:
			balance_numeric = 0
			try:
				if account.raw_data:
					raw_data = json.loads(account.raw_data)
					balance_numeric = float(raw_data.get("balance", 0))
			except (json.JSONDecodeError, ValueError, TypeError):
				pass

			data.append({
				"company": settings.company,
				"iban": account.iban,
				"bank_display": account.bank_display,
				"balance_display": account.balance_display,
				"consent_expires_display": account.consent_expires_display,
				"enabled": account.enabled,
				"uuid": account.uuid,
				"_balance_numeric": balance_numeric
			})

	# Ordina i conti per balance decrescente (dal più alto al più basso)
	# key=lambda x: x["_balance_numeric"] indica il campo da usare per l'ordinamento
	# reverse=True inverte l'ordine (decrescente invece di crescente)
	data.sort(key=lambda x: x["_balance_numeric"], reverse=True)

	return data
