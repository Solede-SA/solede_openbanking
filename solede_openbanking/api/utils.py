# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _


def handle_api_error(response, endpoint_url, operation_name):
	"""
	Gestisce errori API in modo uniforme.

	Args:
		response: Oggetto response di requests
		endpoint_url: URL dell'endpoint chiamato
		operation_name: Nome dell'operazione per i log
	"""
	try:
		error_data = response.json()
		detail = error_data.get('detail', 'Unknown error')
	except:
		detail = f"HTTP {response.status_code}"

	error_title = f"{operation_name} ({response.status_code})"
	error_details = f"URL: {endpoint_url}\nDetail: {detail}"
	frappe.log_error(error_details, error_title)
	frappe.throw(_("Failed to {0} (HTTP {1}): {2}").format(
		operation_name.lower(), response.status_code, detail))


def debug_log(operation_name, **kwargs):
	"""
	Stampa log di debug in formato uniforme.

	Args:
		operation_name: Nome dell'operazione
		**kwargs: Parametri da loggare
	"""
	print("=" * 80)
	print(f"DEBUG - {operation_name}")
	for key, value in kwargs.items():
		# Nasconde token per sicurezza
		if key.lower() == 'token' and value:
			print(f"{key}: {value[:50]}...")
		else:
			print(f"{key}: {value}")
	print("=" * 80)


def validate_company_settings(company):
	"""
	Valida e recupera le impostazioni necessarie per l'azienda.

	Args:
		company: Nome della company

	Returns:
		tuple: (settings, company_doc, fiscal_id)
	"""
	settings = frappe.get_doc("OpenBanking Settings", company)
	company_doc = frappe.get_doc("Company", company)
	fiscal_id = company_doc.tax_id

	if not fiscal_id:
		frappe.throw(_("Tax ID (Partita IVA) not found in Company {0}").format(company))

	if not settings.openbanking_api_url:
		frappe.throw(_("Open Banking API URL not configured in settings"))

	return settings, company_doc, fiscal_id
