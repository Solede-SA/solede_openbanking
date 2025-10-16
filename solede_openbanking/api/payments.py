# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from solede_openbanking.api.client import ACubeAPIClient
from solede_openbanking.api.iban_enrichment import create_bank_and_account_from_iban


@frappe.whitelist()
def get_supplier_bank_accounts(supplier_name):
	"""
	Recupera tutti i Bank Account del fornitore.

	Args:
		supplier_name: Nome del fornitore

	Returns:
		list: Lista di dict con bank account info
	"""
	if not supplier_name:
		frappe.throw(_("Supplier name is required"))

	accounts = frappe.get_all(
		"Bank Account",
		filters={
			"party_type": "Supplier",
			"party": supplier_name,
			"disabled": 0
		},
		fields=["name", "account_name", "iban", "bank", "is_default"]
	)

	# Arricchisci con nome banca
	for account in accounts:
		if account.bank:
			account.bank_name = frappe.db.get_value("Bank", account.bank, "bank_name")

	return accounts


@frappe.whitelist()
def get_company_openbanking_accounts(company):
	"""
	Recupera gli account OpenBanking della company con capabilities.

	Args:
		company: Nome della company

	Returns:
		list: Lista di dict con account OpenBanking e capabilities
	"""
	if not company:
		frappe.throw(_("Company is required"))

	# Recupera OpenBanking Settings
	if not frappe.db.exists("OpenBanking Settings", company):
		frappe.throw(_("OpenBanking Settings not found for company: {0}").format(company))

	settings = frappe.get_doc("OpenBanking Settings", company)

	# Ritorna TUTTI gli accounts abilitati con info su supporto pagamenti
	accounts = []
	for acc in settings.accounts:
		if acc.enabled:
			# Parse raw_data per ottenere capabilities
			capabilities = {"sepa": False, "sepa_instant": False}
			has_payment_support = False

			if acc.raw_data:
				try:
					import json
					raw_data = json.loads(acc.raw_data)

					# Verifica campo "systems" per capabilities pagamenti
					if "systems" in raw_data:
						systems = raw_data.get("systems", [])
						if systems:  # Solo se array non vuoto
							for system in systems:
								system_lower = system.lower() if isinstance(system, str) else ""
								if "sepa-instant" in system_lower or "instant" in system_lower:
									capabilities["sepa_instant"] = True
									has_payment_support = True
								elif "sepa" in system_lower:
									capabilities["sepa"] = True
									has_payment_support = True

				except Exception as e:
					frappe.log_error(f"Error parsing account capabilities: {str(e)}", "Account Capabilities Error")

			# Aggiungi TUTTI gli account, anche quelli senza supporto pagamenti
			accounts.append({
				"uuid": acc.uuid,
				"iban": acc.iban,
				"bank_display": acc.bank_display,
				"balance_display": acc.balance_display,
				"capabilities": capabilities,
				"has_payment_support": has_payment_support
			})

	return accounts


@frappe.whitelist()
def initiate_sepa_payment(reference_doctype, reference_name, account_uuid, creditor_iban,
						  creditor_name=None, use_instant=False):
	"""
	Avvia un pagamento SEPA tramite Open Banking API.
	DRY: Riutilizza ACubeAPIClient e la logica esistente.

	Args:
		reference_doctype: DocType di riferimento (es. "Purchase Invoice")
		reference_name: Nome del documento di riferimento
		account_uuid: UUID dell'account OpenBanking da cui pagare
		creditor_iban: IBAN del beneficiario
		creditor_name: Nome del beneficiario (opzionale)
		use_instant: Se usare SEPA Instant (default: False)

	Returns:
		dict: {
			"payment_name": nome del documento OpenBanking Payment creato,
			"connect_url": URL per autorizzare il pagamento,
			"uuid": UUID del pagamento
		}
	"""
	# Valida input
	if not frappe.db.exists(reference_doctype, reference_name):
		frappe.throw(_("{0} {1} not found").format(reference_doctype, reference_name))

	# Recupera documento di riferimento
	ref_doc = frappe.get_doc(reference_doctype, reference_name)

	# Valida che sia submitted
	if ref_doc.docstatus != 1:
		frappe.throw(_("{0} must be submitted before initiating payment").format(reference_doctype))

	# Valida campi necessari
	if not hasattr(ref_doc, "company"):
		frappe.throw(_("{0} does not have a company field").format(reference_doctype))

	if not hasattr(ref_doc, "grand_total"):
		frappe.throw(_("{0} does not have a grand_total field").format(reference_doctype))

	company = ref_doc.company
	amount = ref_doc.grand_total

	# Valida amount
	if amount <= 0:
		frappe.throw(_("Amount must be greater than 0"))

	if use_instant and amount > 100000:
		frappe.throw(_("SEPA Instant payments cannot exceed 100,000 EUR"))

	# Pulisci IBAN
	creditor_iban_clean = creditor_iban.replace(" ", "").upper()

	# Determina sistema
	system = "sepa-instant" if use_instant else "sepa"

	# Valida capabilities dell'account PRIMA di chiamare API
	if not frappe.db.exists("OpenBanking Settings", company):
		frappe.throw(_("OpenBanking Settings not found for company: {0}").format(company))

	settings = frappe.get_doc("OpenBanking Settings", company)
	account_found = False
	account_capabilities = None

	for acc in settings.accounts:
		if acc.uuid == account_uuid:
			account_found = True
			# Parse capabilities
			if acc.raw_data:
				try:
					raw_data = json.loads(acc.raw_data)

					# Verifica campo "systems" per capabilities pagamenti
					if "systems" in raw_data:
						systems = raw_data.get("systems", [])
						has_sepa = False
						has_sepa_instant = False

						# Log systems disponibili
						frappe.log_error(
							f"Account UUID: {account_uuid}\n"
							f"Systems: {systems}",
							"Payment Systems Check"
						)

						# Verifica se array vuoto
						if not systems:
							frappe.throw(_(
								"L'account selezionato non supporta pagamenti. "
								"Questo account è configurato solo per la lettura delle transazioni. "
								"Seleziona un account con supporto pagamenti abilitato."
							))

						for system in systems:
							system_lower = system.lower() if isinstance(system, str) else ""
							if "sepa-instant" in system_lower or "instant" in system_lower:
								has_sepa_instant = True
							elif "sepa" in system_lower:
								has_sepa = True

						# Verifica se l'account supporta il sistema richiesto
						if use_instant and not has_sepa_instant:
							frappe.throw(_(
								"L'account selezionato non supporta bonifici SEPA Instant. "
								"Sistemi disponibili: {0}. "
								"Seleziona un altro account oppure deseleziona l'opzione Bonifico Istantaneo."
							).format(", ".join(systems)))
						elif not use_instant and not has_sepa:
							frappe.throw(_(
								"L'account selezionato non supporta bonifici SEPA standard. "
								"Sistemi disponibili: {0}. "
								"Seleziona un altro account."
							).format(", ".join(systems)))
					else:
						# Campo systems non trovato
						frappe.throw(_(
							"Impossibile verificare le capabilities di pagamento per questo account. "
							"Il campo 'systems' non è presente nei dati dell'account."
						))

				except json.JSONDecodeError as e:
					frappe.log_error(f"Error parsing account raw_data: {str(e)}", "Account Validation Error")
					frappe.throw(_("Errore nella validazione capabilities dell'account"))
			else:
				frappe.log_error(
					f"WARNING: No raw_data found for account {account_uuid}",
					"No Raw Data"
				)
			break

	if not account_found:
		frappe.throw(_("Account OpenBanking non trovato: {0}").format(account_uuid))

	# Prepara descrizione
	description = f"{reference_doctype} {reference_name}"
	if hasattr(ref_doc, "title"):
		description = f"{ref_doc.title}"

	# Crea client API
	client = ACubeAPIClient(company)

	# Prepara return URL e error URL
	site_url = frappe.utils.get_url()
	return_url = f"{site_url}/payment-callback"
	error_url = f"{site_url}/payment-callback"

	# Prepara payload
	payload = {
		"amount": str(amount),
		"currencyCode": "EUR",
		"description": description[:1000],  # Max 1000 chars
		"accountUuid": account_uuid,
		"creditorIban": creditor_iban_clean,
		"creditorName": creditor_name or "Supplier",
		"returnUrl": return_url,
		"errorUrl": error_url
	}

	# Chiama API
	endpoint = f"payments/send/{system}"
	response = client.post(endpoint, f"Initiate {system.upper()} Payment", payload=payload)

	if not response or "uuid" not in response:
		frappe.throw(_("API did not return payment UUID"))

	# Crea record OpenBanking Payment
	payment_doc = frappe.get_doc({
		"doctype": "OpenBanking Payment",
		"uuid": response.get("uuid"),
		"payment_direction": "outbound",
		"status": "pending",
		"system": system,
		"amount": amount,
		"currency_code": "EUR",
		"description": description,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"company": company,
		"supplier": ref_doc.get("supplier"),
		"creditor_name": creditor_name,
		"creditor_iban": creditor_iban_clean,
		"account_uuid": account_uuid,
		"connect_url": response.get("connectUrl"),
		"raw_response": json.dumps(response, indent=2)
	})

	payment_doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"payment_name": payment_doc.name,
		"connect_url": response.get("connectUrl"),
		"uuid": response.get("uuid")
	}


@frappe.whitelist()
def get_payment_status(payment_uuid):
	"""
	Recupera lo status di un pagamento dall'API e aggiorna il record locale.
	DRY: Riutilizza ACubeAPIClient.

	Args:
		payment_uuid: UUID del pagamento

	Returns:
		dict: Status aggiornato del pagamento
	"""
	if not payment_uuid:
		frappe.throw(_("Payment UUID is required"))

	# Trova OpenBanking Payment
	payment_name = frappe.db.get_value("OpenBanking Payment", {"uuid": payment_uuid}, "name")
	if not payment_name:
		frappe.throw(_("OpenBanking Payment not found for UUID: {0}").format(payment_uuid))

	payment_doc = frappe.get_doc("OpenBanking Payment", payment_name)

	# Crea client API
	client = ACubeAPIClient(payment_doc.company)

	# Chiama API
	endpoint = f"payments/{payment_uuid}"
	response = client.get(endpoint, "Get Payment Status")

	if not response:
		frappe.throw(_("API did not return payment status"))

	# Aggiorna record
	old_status = payment_doc.status
	new_status = response.get("status", "pending")

	payment_doc.status = new_status
	payment_doc.end_to_end_id = response.get("endToEndId")
	payment_doc.raw_response = json.dumps(response, indent=2)

	payment_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"payment_name": payment_doc.name,
		"old_status": old_status,
		"new_status": new_status,
		"response": response
	}


@frappe.whitelist()
def create_or_get_supplier_bank_account(supplier_name, iban, account_name=None):
	"""
	Crea o recupera un Bank Account per il fornitore.
	DRY: Riutilizza completamente la funzione esistente da iban_enrichment.

	Args:
		supplier_name: Nome del fornitore
		iban: IBAN del fornitore
		account_name: Nome dell'account (opzionale)

	Returns:
		dict: Bank Account info
	"""
	# DRY: Riutilizzo totale della funzione esistente
	bank_account = create_bank_and_account_from_iban(
		iban=iban,
		party_type="Supplier",
		party=supplier_name,
		account_name=account_name
	)

	return {
		"name": bank_account.name,
		"account_name": bank_account.account_name,
		"iban": bank_account.iban,
		"bank": bank_account.bank
	}
