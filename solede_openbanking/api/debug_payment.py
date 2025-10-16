# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from solede_openbanking.api.client import ACubeAPIClient


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


@frappe.whitelist()
def debug_payment_request(company, account_uuid, creditor_iban, amount="10.00", use_instant=False):
	"""
	Script di debug per testare la chiamata API di pagamento.
	Mostra tutti i dettagli della richiesta senza creare documenti.

	Args:
		company: Nome della company
		account_uuid: UUID dell'account OpenBanking
		creditor_iban: IBAN del beneficiario
		amount: Importo (default: 10.00)
		use_instant: Se usare SEPA Instant (default: False)

	Returns:
		dict: Dettagli completi della richiesta e risposta
	"""
	try:
		# Crea client
		client = ACubeAPIClient(company)

		# Determina sistema
		system = "sepa-instant" if use_instant else "sepa"

		# Prepara return URL e error URL
		site_url = frappe.utils.get_url()
		return_url = f"{site_url}/payment-callback"
		error_url = f"{site_url}/payment-callback"

		# Pulisci IBAN
		creditor_iban_clean = creditor_iban.replace(" ", "").upper()

		# Prepara payload
		payload = {
			"amount": str(amount),
			"currencyCode": "EUR",
			"description": "Test Payment",
			"accountUuid": account_uuid,
			"creditorIban": creditor_iban_clean,
			"creditorName": "Test Creditor",
			"returnUrl": return_url,
			"errorUrl": error_url
		}

		# Costruisci endpoint
		endpoint = f"payments/send/{system}"
		url = client.build_url(endpoint)

		# Info di debug
		debug_info = {
			"company": company,
			"fiscal_id": client.fiscal_id,
			"api_base_url": client.settings.openbanking_api_url,
			"full_url": url,
			"endpoint": endpoint,
			"system": system,
			"token": client.token[:50] + "..." if client.token else "MISSING",
			"payload": payload,
			"headers": {
				"Authorization": "Bearer " + (client.token[:50] + "..." if client.token else "MISSING"),
				"Content-Type": "application/json"
			}
		}

		print("=" * 80)
		print("DEBUG PAYMENT REQUEST")
		print("=" * 80)
		print(json.dumps(debug_info, indent=2))
		print("=" * 80)

		# Effettua la chiamata
		try:
			response = client.post(endpoint, f"Test {system.upper()} Payment", payload=payload)

			result = {
				"success": True,
				"debug_info": debug_info,
				"response": response
			}

			print("=" * 80)
			print("RESPONSE SUCCESS")
			print(json.dumps(response, indent=2))
			print("=" * 80)

			return result

		except Exception as api_error:
			error_msg = str(api_error)

			result = {
				"success": False,
				"debug_info": debug_info,
				"error": error_msg
			}

			print("=" * 80)
			print("RESPONSE ERROR")
			print(error_msg)
			print("=" * 80)

			return result

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Debug Payment Error: {error_msg}", "Debug Payment")

		return {
			"success": False,
			"error": error_msg,
			"message": "Errore durante il debug della richiesta di pagamento"
		}


@frappe.whitelist()
def verify_settings(company):
	"""
	Verifica la configurazione di OpenBanking Settings.

	Args:
		company: Nome della company

	Returns:
		dict: Dettagli della configurazione
	"""
	try:
		settings = frappe.get_doc("OpenBanking Settings", company)
		company_doc = frappe.get_doc("Company", company)

		config = {
			"company": company,
			"tax_id": company_doc.tax_id,
			"api_url": settings.openbanking_api_url,
			"email": settings.email,
			"business_registry_created": settings.business_registry_created,
			"enabled_accounts_count": len([acc for acc in settings.accounts if acc.enabled]),
			"total_accounts_count": len(settings.accounts),
			"accounts": []
		}

		# Aggiungi dettagli account
		for acc in settings.accounts:
			if acc.enabled:
				account_info = {
					"uuid": acc.uuid,
					"iban": acc.iban,
					"bank": acc.bank_display,
					"enabled": acc.enabled
				}

				# Parse raw_data per capabilities
				if acc.raw_data:
					try:
						raw_data = json.loads(acc.raw_data)
						account_info["systems"] = raw_data.get("systems", [])
					except:
						account_info["systems"] = "Error parsing raw_data"

				config["accounts"].append(account_info)

		print("=" * 80)
		print("OPENBANKING SETTINGS VERIFICATION")
		print("=" * 80)
		print(json.dumps(config, indent=2))
		print("=" * 80)

		return {
			"success": True,
			"config": config
		}

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Verify Settings Error: {error_msg}", "Verify Settings")

		return {
			"success": False,
			"error": error_msg
		}
