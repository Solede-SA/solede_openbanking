# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import requests
import re
from datetime import datetime
from frappe import _
from solede_openbanking.api.authentication import get_valid_token


def parse_iso_datetime(iso_string):
    """
    Converte una stringa datetime ISO 8601 (con Z) in formato MySQL.

    Args:
        iso_string: Stringa in formato ISO 8601 (es. "2026-01-11T14:51:05Z")

    Returns:
        Stringa in formato MySQL (es. "2026-01-11 14:51:05")
    """
    if not iso_string:
        return None

    try:
        # Rimuovi la Z e converti in datetime
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        # Restituisci nel formato MySQL
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        frappe.log_error(f"Error parsing datetime: {iso_string}, Error: {str(e)}", "DateTime Parse Error")
        return None


def validate_password(password):
    """
    Valida che la password rispetti i requisiti:
    - Almeno 1 carattere maiuscolo
    - Almeno 1 carattere minuscolo
    - Almeno 1 numero
    - Almeno 1 carattere speciale (!@#$%^&*()_+-=[]{}|;:,.<>?)
    """
    pattern = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])(?=.*[!@#$%^&*()_+\-=\[\]{}|;:,.<>?])'

    if not re.search(pattern, password):
        frappe.throw(_("Password must contain at least 1 uppercase letter, 1 lowercase letter, 1 number, and 1 special character"))

    return True


@frappe.whitelist()
def create_business_registry(company, password):
    """
    Crea un nuovo Business Registry per l'azienda specificata.
    Nota: questa operazione comporta un addebito.

    Args:
        company: Nome della company
        password: Password per il nuovo account Business Registry (non usata in questa versione)
    """
    # Ottieni le impostazioni
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Ottieni i dati dalla Company
    company_doc = frappe.get_doc("Company", company)
    fiscal_id = company_doc.tax_id

    if not fiscal_id:
        frappe.throw(_("Tax ID (Partita IVA) not found in Company {0}").format(company))

    if not company_doc.company_name:
        frappe.throw(_("Company name not found in Company {0}").format(company))

    # Verifica che l'Open Banking API URL sia configurato
    if not settings.openbanking_api_url:
        frappe.throw(_("Open Banking API URL not configured in settings"))

    # Verifica che l'email sia configurata
    if not settings.email:
        frappe.throw(_("Email not configured in OpenBanking Settings"))

    # Ottieni un token valido
    token = get_valid_token(company)

    # Prepara l'URL per creare il Business Registry
    endpoint_url = f"{settings.openbanking_api_url.rstrip('/')}/business-registry"

    # Debug prints
    print("=" * 80)
    print(f"DEBUG - Create Business Registry")
    print(f"Company: {company}")
    print(f"Fiscal ID: {fiscal_id}")
    print(f"Business Name: {company_doc.company_name}")
    print(f"Email: {settings.email}")
    print(f"Open Banking API URL: {settings.openbanking_api_url}")
    print(f"Full Endpoint URL: {endpoint_url}")
    print(f"Token (first 50 chars): {token[:50]}...")
    print("=" * 80)

    # Prepara il payload per creare il Business Registry
    payload = {
        "fiscalId": fiscal_id,
        "businessName": company_doc.company_name,
        "email": settings.email,
        "emailAlerts": True,
        "locale": "it",
        "country": "IT",
        "enabled": True
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:

        # Effettua la richiesta
        response = requests.post(endpoint_url, json=payload, headers=headers, timeout=30)

        print(f"Response Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        try:
            print(f"Response Body: {response.text}")
        except:
            print("Response Body: (unable to read)")

        # Verifica lo status code (201 = created)
        if response.status_code == 201:
            # Estrai i dati della risposta
            response_data = response.json()

            print(f"DEBUG - Response data: {response_data}")

            # Segna il Business Registry come creato
            settings.business_registry_created = 1
            settings.save(ignore_permissions=True)
            frappe.db.commit()

            print(f"DEBUG - Business Registry marked as created")

            return {
                "success": True,
                "message": _("Business Registry created successfully"),
                "data": response_data
            }
        else:
            # Gestisci altri status code
            status_code = response.status_code

            try:
                error_data = response.json()
                detail = error_data.get('detail', 'Unknown error')
            except:
                detail = f"HTTP {status_code}"

            # Log breve per evitare errori di lunghezza
            error_title = f"Business Registry ({status_code})"
            error_details = f"URL: {endpoint_url}\nDetail: {detail}"
            frappe.log_error(error_details, error_title)

            # Messaggio utente più chiaro
            frappe.throw(_("Failed to create Business Registry (HTTP {0}): {1}").format(status_code, detail))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Business Registry API Error")
        frappe.throw(_("Failed to connect to Business Registry API: {0}").format(error_msg))


@frappe.whitelist()
def get_business_registry_info(company):
    """
    Recupera le informazioni del Business Registry per l'azienda specificata.

    Args:
        company: Nome della company
    """
    # Ottieni le impostazioni
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Ottieni il fiscal ID dalla Company
    company_doc = frappe.get_doc("Company", company)
    fiscal_id = company_doc.tax_id

    if not fiscal_id:
        frappe.throw(_("Tax ID (Partita IVA) not found in Company {0}").format(company))

    # Verifica che l'Open Banking API URL sia configurato
    if not settings.openbanking_api_url:
        frappe.throw(_("Open Banking API URL not configured in settings"))

    # Ottieni un token valido
    token = get_valid_token(company)

    # Prepara l'URL per recuperare il Business Registry
    endpoint_url = f"{settings.openbanking_api_url.rstrip('/')}/business-registry/{fiscal_id}"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        # Effettua la richiesta GET
        response = requests.get(endpoint_url, headers=headers, timeout=30)

        print(f"DEBUG - Get Business Registry Info")
        print(f"URL: {endpoint_url}")
        print(f"Status Code: {response.status_code}")

        # Verifica lo status code (200 = success)
        if response.status_code == 200:
            response_data = response.json()
            print(f"Response data: {response_data}")

            return {
                "success": True,
                "data": response_data
            }
        elif response.status_code == 404:
            frappe.throw(_("Business Registry not found. Please create it first."))
        else:
            # Gestisci altri status code
            try:
                error_data = response.json()
                detail = error_data.get('detail', 'Unknown error')
            except:
                detail = f"HTTP {response.status_code}"

            frappe.throw(_("Failed to retrieve Business Registry (HTTP {0}): {1}").format(response.status_code, detail))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Business Registry GET Error")
        frappe.throw(_("Failed to connect to Business Registry API: {0}").format(error_msg))


@frappe.whitelist()
def start_connect_request(company, return_url=None, bank_manager_email=None, days=180, test_mode=0):
    """
    Avvia il processo di connessione bancaria per il Business Registry.
    Restituisce un URL dove l'utente può selezionare la banca e autorizzare l'accesso.

    Args:
        company: Nome della company
        return_url: URL opzionale dove tornare dopo la connessione
        bank_manager_email: Email opzionale del manager che gestisce la connessione
        days: Numero di giorni per il consenso (1-180, default 180)
        test_mode: Se 1, usa banca fake per test (country code XF)
    """
    # Ottieni le impostazioni
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Ottieni il fiscal ID dalla Company
    company_doc = frappe.get_doc("Company", company)
    fiscal_id = company_doc.tax_id

    if not fiscal_id:
        frappe.throw(_("Tax ID (Partita IVA) not found in Company {0}").format(company))

    # Verifica che l'Open Banking API URL sia configurato
    if not settings.openbanking_api_url:
        frappe.throw(_("Open Banking API URL not configured in settings"))

    # Ottieni un token valido
    token = get_valid_token(company)

    # Prepara l'URL per la connect request
    endpoint_url = f"{settings.openbanking_api_url.rstrip('/')}/business-registry/{fiscal_id}/connect"

    # Determina il country code in base al test_mode
    # XF = Fake bank per test (solo in sandbox)
    # IT = Banche reali italiane
    country_code = "XF" if int(test_mode) == 1 else "IT"

    # Prepara il payload
    payload = {
        "locale": "it",
        "country": country_code,
        "days": int(days)
    }

    # Aggiungi parametri opzionali se forniti
    if return_url:
        payload["returnUrl"] = return_url
    if bank_manager_email:
        payload["bankManagerEmail"] = bank_manager_email

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    print("=" * 80)
    print(f"DEBUG - Start Connect Request")
    print(f"Test Mode: {test_mode}")
    print(f"Country Code: {country_code}")
    print(f"Endpoint URL: {endpoint_url}")
    print(f"Payload: {payload}")
    print("=" * 80)

    try:
        # Effettua la richiesta POST
        response = requests.post(endpoint_url, json=payload, headers=headers, timeout=30)

        print(f"Response Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")

        # Verifica lo status code (201 = created)
        if response.status_code == 201:
            response_data = response.json()
            connect_url = response_data.get("connectUrl")

            if not connect_url:
                frappe.throw(_("Connect URL not found in response"))

            return {
                "success": True,
                "connect_url": connect_url,
                "message": _("Connect request created successfully")
            }
        else:
            # Gestisci altri status code
            try:
                error_data = response.json()
                detail = error_data.get('detail', 'Unknown error')
            except:
                detail = f"HTTP {response.status_code}"

            error_title = f"Connect Request ({response.status_code})"
            error_details = f"URL: {endpoint_url}\nDetail: {detail}"
            frappe.log_error(error_details, error_title)
            frappe.throw(_("Failed to create connect request (HTTP {0}): {1}").format(response.status_code, detail))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Connect Request API Error")
        frappe.throw(_("Failed to connect to Business Registry API: {0}").format(error_msg))


@frappe.whitelist()
def get_accounts(company):
    """
    Recupera tutti gli account bancari autorizzati per il Business Registry.
    Aggiorna la child table degli account nel documento OpenBanking Settings.

    Args:
        company: Nome della company
    """
    # Ottieni le impostazioni
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Ottieni il fiscal ID dalla Company
    company_doc = frappe.get_doc("Company", company)
    fiscal_id = company_doc.tax_id

    if not fiscal_id:
        frappe.throw(_("Tax ID (Partita IVA) not found in Company {0}").format(company))

    # Verifica che l'Open Banking API URL sia configurato
    if not settings.openbanking_api_url:
        frappe.throw(_("Open Banking API URL not configured in settings"))

    # Ottieni un token valido
    token = get_valid_token(company)

    # Prepara l'URL per recuperare gli account
    endpoint_url = f"{settings.openbanking_api_url.rstrip('/')}/business-registry/{fiscal_id}/accounts"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("=" * 80)
    print(f"DEBUG - Get Accounts")
    print(f"Endpoint URL: {endpoint_url}")
    print("=" * 80)

    try:
        # Effettua la richiesta GET
        response = requests.get(endpoint_url, headers=headers, timeout=30)

        print(f"Response Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")

        # Verifica lo status code (200 = success)
        if response.status_code == 200:
            accounts_data = response.json()

            # Pulisci la tabella esistente
            settings.accounts = []

            # Aggiungi gli account alla child table
            for account in accounts_data:
                settings.append("accounts", {
                    "uuid": account.get("uuid"),
                    "account_id": account.get("accountId"),
                    "iban": account.get("iban"),
                    "account_name": account.get("name"),
                    "provider_name": account.get("providerName"),
                    "provider_country": account.get("providerCountry"),
                    "nature": account.get("nature"),
                    "balance": account.get("balance"),
                    "currency_code": account.get("currencyCode"),
                    "enabled": 1 if account.get("enabled") else 0,
                    "consent_expires_at": parse_iso_datetime(account.get("consentExpiresAt"))
                })

            # Salva il documento
            settings.save(ignore_permissions=True)
            frappe.db.commit()

            return {
                "success": True,
                "message": _("Retrieved {0} accounts").format(len(accounts_data)),
                "count": len(accounts_data)
            }
        elif response.status_code == 404:
            frappe.throw(_("No accounts found. Please connect a bank account first."))
        else:
            # Gestisci altri status code
            try:
                error_data = response.json()
                detail = error_data.get('detail', 'Unknown error')
            except:
                detail = f"HTTP {response.status_code}"

            error_title = f"Get Accounts ({response.status_code})"
            error_details = f"URL: {endpoint_url}\nDetail: {detail}"
            frappe.log_error(error_details, error_title)
            frappe.throw(_("Failed to retrieve accounts (HTTP {0}): {1}").format(response.status_code, detail))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Get Accounts API Error")
        frappe.throw(_("Failed to connect to Business Registry API: {0}").format(error_msg))


@frappe.whitelist()
def toggle_account(company, uuid, enabled):
    """
    Abilita o disabilita un account bancario.
    Disabilitare un account cancella anche il saldo, i dati extra e le transazioni.

    Args:
        company: Nome della company
        uuid: UUID dell'account da abilitare/disabilitare
        enabled: 1 per abilitare, 0 per disabilitare
    """
    # Ottieni le impostazioni
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Verifica che l'Open Banking API URL sia configurato
    if not settings.openbanking_api_url:
        frappe.throw(_("Open Banking API URL not configured in settings"))

    # Ottieni un token valido
    token = get_valid_token(company)

    # Prepara l'URL per l'aggiornamento dell'account
    endpoint_url = f"{settings.openbanking_api_url.rstrip('/')}/accounts/{uuid}"

    payload = {
        "enabled": bool(int(enabled))
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    print("=" * 80)
    print(f"DEBUG - Toggle Account")
    print(f"UUID: {uuid}")
    print(f"Enabled: {enabled}")
    print(f"Endpoint URL: {endpoint_url}")
    print(f"Payload: {payload}")
    print("=" * 80)

    try:
        # Effettua la richiesta PUT
        response = requests.put(endpoint_url, json=payload, headers=headers, timeout=30)

        print(f"Response Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")

        # Verifica lo status code (200 = success)
        if response.status_code == 200:
            response_data = response.json()

            # Aggiorna direttamente il campo enabled nella child table usando db.set_value
            # Questo evita conflitti di concorrenza quando si abilitano/disabilitano più account rapidamente
            for account in settings.accounts:
                if account.uuid == uuid:
                    frappe.db.set_value("OpenBanking Account", account.name, "enabled", int(enabled))
                    break

            frappe.db.commit()

            action = "enabled" if int(enabled) == 1 else "disabled"
            return {
                "success": True,
                "message": _("Account {0} successfully").format(action),
                "data": response_data
            }
        else:
            # Gestisci altri status code
            try:
                error_data = response.json()
                detail = error_data.get('detail', 'Unknown error')
            except:
                detail = f"HTTP {response.status_code}"

            error_title = f"Toggle Account ({response.status_code})"
            error_details = f"URL: {endpoint_url}\nDetail: {detail}"
            frappe.log_error(error_details, error_title)
            frappe.throw(_("Failed to toggle account (HTTP {0}): {1}").format(response.status_code, detail))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Toggle Account API Error")
        frappe.throw(_("Failed to connect to API: {0}").format(error_msg))


@frappe.whitelist()
def delete_account(company, uuid):
    """
    Elimina un account bancario e tutti gli account associati alla stessa connessione bancaria.
    Tutti gli account devono essere disabilitati e non avere pagamenti collegati.

    Args:
        company: Nome della company
        uuid: UUID dell'account da eliminare
    """
    # Ottieni le impostazioni
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Verifica che l'Open Banking API URL sia configurato
    if not settings.openbanking_api_url:
        frappe.throw(_("Open Banking API URL not configured in settings"))

    # Ottieni un token valido
    token = get_valid_token(company)

    # Prepara l'URL per eliminare l'account
    endpoint_url = f"{settings.openbanking_api_url.rstrip('/')}/accounts/{uuid}"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("=" * 80)
    print(f"DEBUG - Delete Account")
    print(f"UUID: {uuid}")
    print(f"Endpoint URL: {endpoint_url}")
    print("=" * 80)

    try:
        # Effettua la richiesta DELETE
        response = requests.delete(endpoint_url, headers=headers, timeout=30)

        print(f"Response Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")

        # Verifica lo status code (202 = accepted)
        if response.status_code == 202:
            response_data = response.json()
            removed_accounts = response_data.get("removedAccounts", [])

            # Rimuovi gli account dalla child table
            accounts_to_keep = []
            for account in settings.accounts:
                if account.uuid not in removed_accounts:
                    accounts_to_keep.append(account)

            settings.accounts = []
            for account in accounts_to_keep:
                settings.append("accounts", account.as_dict())

            settings.save(ignore_permissions=True)
            frappe.db.commit()

            return {
                "success": True,
                "message": _("Account deleted successfully. {0} account(s) removed.").format(len(removed_accounts)),
                "removed_accounts": removed_accounts
            }
        else:
            # Gestisci altri status code
            try:
                error_data = response.json()
                detail = error_data.get('detail', 'Unknown error')
            except:
                detail = f"HTTP {response.status_code}"

            error_title = f"Delete Account ({response.status_code})"
            error_details = f"URL: {endpoint_url}\nDetail: {detail}"
            frappe.log_error(error_details, error_title)
            frappe.throw(_("Failed to delete account (HTTP {0}): {1}").format(response.status_code, detail))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Delete Account API Error")
        frappe.throw(_("Failed to connect to API: {0}").format(error_msg))


@frappe.whitelist()
def get_transactions(company, account_uuid=None, from_date=None, to_date=None, page=1, items_per_page=30):
	"""
	Recupera le transazioni bancarie dal Business Registry ACube.
	Se non specificato, recupera le transazioni del mese corrente.

	Args:
		company: Nome della company
		account_uuid: UUID account specifico (opzionale, se None prende tutti gli account abilitati)
		from_date: Data inizio (formato YYYY-MM-DD)
		to_date: Data fine (formato YYYY-MM-DD)
		page: Numero pagina (default 1)
		items_per_page: Items per pagina (default 30, max 100)

	Returns:
		dict: {
			"success": True,
			"transactions": [...],
			"total": count,
			"page": page,
			"items_per_page": items_per_page
		}
	"""
	# Ottieni le impostazioni
	settings = frappe.get_doc("OpenBanking Settings", company)

	# Ottieni il fiscal ID dalla Company
	company_doc = frappe.get_doc("Company", company)
	fiscal_id = company_doc.tax_id

	if not fiscal_id:
		frappe.throw(_("Tax ID (Partita IVA) not found in Company {0}").format(company))

	# Verifica che l'Open Banking API URL sia configurato
	if not settings.openbanking_api_url:
		frappe.throw(_("Open Banking API URL not configured in settings"))

	# Ottieni un token valido
	token = get_valid_token(company)

	# Prepara l'URL per recuperare le transazioni
	endpoint_url = f"{settings.openbanking_api_url.rstrip('/')}/business-registry/{fiscal_id}/transactions"

	# Prepara i parametri query
	params = {
		"page": page,
		"itemsPerPage": min(int(items_per_page), 100)  # Max 100
	}

	# Aggiungi filtro account se specificato
	if account_uuid:
		params["account.uuid"] = account_uuid

	# Aggiungi filtri data se specificati
	if from_date:
		params["madeOn[after]"] = from_date
	if to_date:
		params["madeOn[before]"] = to_date

	headers = {
		"Authorization": f"Bearer {token}"
	}

	print("=" * 80)
	print(f"DEBUG - Get Transactions")
	print(f"Endpoint URL: {endpoint_url}")
	print(f"Params: {params}")
	print("=" * 80)

	try:
		# Effettua la richiesta GET
		response = requests.get(endpoint_url, headers=headers, params=params, timeout=30)

		print(f"Response Status Code: {response.status_code}")
		print(f"Response Body (first 500 chars): {response.text[:500]}")

		# Verifica lo status code (200 = success)
		if response.status_code == 200:
			transactions_data = response.json()

			return {
				"success": True,
				"transactions": transactions_data,
				"total": len(transactions_data),
				"page": page,
				"items_per_page": items_per_page
			}
		elif response.status_code == 404:
			# Nessuna transazione trovata
			return {
				"success": True,
				"transactions": [],
				"total": 0,
				"page": page,
				"items_per_page": items_per_page
			}
		else:
			# Gestisci altri status code
			try:
				error_data = response.json()
				detail = error_data.get('detail', 'Unknown error')
			except:
				detail = f"HTTP {response.status_code}"

			error_title = f"Get Transactions ({response.status_code})"
			error_details = f"URL: {endpoint_url}\nParams: {params}\nDetail: {detail}"
			frappe.log_error(error_details, error_title)
			frappe.throw(_("Failed to retrieve transactions (HTTP {0}): {1}").format(response.status_code, detail))

	except requests.exceptions.RequestException as e:
		error_msg = str(e)
		frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Get Transactions API Error")
		frappe.throw(_("Failed to connect to API: {0}").format(error_msg))


def parse_date(date_string):
	"""
	Converte una stringa data in formato MySQL date.

	Args:
		date_string: Stringa data (formato YYYY-MM-DD o ISO)

	Returns:
		Stringa in formato YYYY-MM-DD o None
	"""
	if not date_string:
		return None

	try:
		# Se è già in formato YYYY-MM-DD
		if len(date_string) == 10:
			return date_string
		# Se è ISO datetime, prendi solo la data
		dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
		return dt.strftime('%Y-%m-%d')
	except Exception as e:
		frappe.log_error(f"Error parsing date: {date_string}, Error: {str(e)}", "Date Parse Error")
		return None


@frappe.whitelist()
def import_transactions(company, account_uuid=None, from_date=None, to_date=None):
	"""
	Importa le transazioni da ACube API in Bank Transaction.
	Crea anche log entries in ACube Transaction Log.

	Args:
		company: Nome della company
		account_uuid: UUID account specifico (opzionale)
		from_date: Data inizio (formato YYYY-MM-DD)
		to_date: Data fine (formato YYYY-MM-DD)

	Returns:
		dict: {
			"success": True,
			"imported": count,
			"skipped": count,
			"failed": count,
			"message": "..."
		}
	"""
	imported_count = 0
	skipped_count = 0
	failed_count = 0

	# Ottieni le impostazioni
	settings = frappe.get_doc("OpenBanking Settings", company)

	# Se non specificato account_uuid, prendi tutti gli account abilitati
	account_uuids = []
	if account_uuid:
		account_uuids = [account_uuid]
	else:
		# Prendi tutti gli account abilitati
		for account in settings.accounts:
			if account.enabled:
				account_uuids.append(account.uuid)

	if not account_uuids:
		frappe.throw(_("No enabled accounts found. Please enable at least one account."))

	print(f"DEBUG - Importing transactions for {len(account_uuids)} account(s)")

	# Per ogni account, recupera e importa le transazioni
	for acc_uuid in account_uuids:
		try:
			# Recupera transazioni per questo account
			result = get_transactions(
				company=company,
				account_uuid=acc_uuid,
				from_date=from_date,
				to_date=to_date,
				page=1,
				items_per_page=100
			)

			if not result.get("success"):
				failed_count += len(account_uuids)
				continue

			transactions = result.get("transactions", [])
			print(f"DEBUG - Found {len(transactions)} transactions for account {acc_uuid}")

			# Trova l'account nella child table per ottenere info
			account_info = None
			for acc in settings.accounts:
				if acc.uuid == acc_uuid:
					account_info = acc
					break

			if not account_info:
				print(f"WARNING - Account {acc_uuid} not found in settings")
				continue

			# Trova il Bank Account ERPNext corrispondente all'IBAN
			bank_account = None
			if account_info.iban:
				bank_account = frappe.db.get_value(
					"Bank Account",
					{"iban": account_info.iban, "company": company},
					"name"
				)

			if not bank_account:
				print(f"WARNING - No Bank Account found for IBAN {account_info.iban}")
				# Prova a trovare un bank account generico per la company
				bank_account = frappe.db.get_value(
					"Bank Account",
					{"company": company, "is_default": 1},
					"name"
				)

			# Importa ogni transazione
			for txn in transactions:
				try:
					# Log della transazione
					log_entry = create_transaction_log(
						company=company,
						account_uuid=acc_uuid,
						transaction_data=txn,
						bank_account=bank_account
					)

					# Controlla se esiste già
					existing = frappe.db.exists(
						"Bank Transaction",
						{"acube_transaction_id": txn.get("transactionId")}
					)

					if existing:
						print(f"DEBUG - Transaction {txn.get('transactionId')} already exists, skipping")
						frappe.db.set_value("ACube Transaction Log", log_entry.name, "import_status", "Skipped")
						frappe.db.set_value("ACube Transaction Log", log_entry.name, "error_message", "Transaction already imported")
						skipped_count += 1
						continue

					# Crea Bank Transaction
					bank_txn = create_bank_transaction_from_acube(
						company=company,
						bank_account=bank_account,
						account_info=account_info,
						transaction_data=txn
					)

					# Aggiorna log con successo
					frappe.db.set_value("ACube Transaction Log", log_entry.name, "import_status", "Imported")
					frappe.db.set_value("ACube Transaction Log", log_entry.name, "bank_transaction", bank_txn.name)

					imported_count += 1
					print(f"DEBUG - Imported transaction {bank_txn.name}")

				except Exception as e:
					error_msg = str(e)
					print(f"ERROR - Failed to import transaction: {error_msg}")
					frappe.log_error(f"Transaction: {txn}, Error: {error_msg}", "Import Transaction Error")

					# Aggiorna log con errore
					if log_entry:
						frappe.db.set_value("ACube Transaction Log", log_entry.name, "import_status", "Failed")
						frappe.db.set_value("ACube Transaction Log", log_entry.name, "error_message", error_msg[:500])

					failed_count += 1
					continue

		except Exception as e:
			error_msg = str(e)
			print(f"ERROR - Failed to process account {acc_uuid}: {error_msg}")
			frappe.log_error(f"Account: {acc_uuid}, Error: {error_msg}", "Import Account Error")
			failed_count += 1
			continue

	frappe.db.commit()

	message = _("Import completed: {0} imported, {1} skipped, {2} failed").format(
		imported_count, skipped_count, failed_count
	)

	return {
		"success": True,
		"imported": imported_count,
		"skipped": skipped_count,
		"failed": failed_count,
		"message": message
	}


def create_transaction_log(company, account_uuid, transaction_data, bank_account=None):
	"""
	Crea un log entry per la transazione.

	Args:
		company: Company
		account_uuid: UUID account ACube
		transaction_data: Dati transazione da API
		bank_account: Bank Account ERPNext (opzionale)

	Returns:
		ACube Transaction Log document
	"""
	log = frappe.get_doc({
		"doctype": "ACube Transaction Log",
		"company": company,
		"bank_account": bank_account,
		"acube_account_uuid": account_uuid,
		"transaction_date": parse_date(transaction_data.get("madeOn")),
		"acube_transaction_id": transaction_data.get("transactionId"),
		"transaction_status": transaction_data.get("status"),
		"amount": abs(float(transaction_data.get("amount", 0))),
		"currency": transaction_data.get("currencyCode"),
		"import_status": "Pending",
		"raw_data": transaction_data
	})
	log.insert(ignore_permissions=True)
	return log


def create_bank_transaction_from_acube(company, bank_account, account_info, transaction_data):
	"""
	Crea un Bank Transaction da dati ACube.

	Args:
		company: Company
		bank_account: Bank Account ERPNext
		account_info: Info account dalla child table
		transaction_data: Dati transazione da API

	Returns:
		Bank Transaction document
	"""
	amount = float(transaction_data.get("amount", 0))

	# Determina deposit/withdrawal
	deposit = amount if amount > 0 else 0
	withdrawal = abs(amount) if amount < 0 else 0

	# Crea Bank Transaction
	bank_txn = frappe.get_doc({
		"doctype": "Bank Transaction",
		"date": parse_date(transaction_data.get("madeOn")),
		"status": "Pending",
		"bank_account": bank_account,
		"company": company,
		"deposit": deposit,
		"withdrawal": withdrawal,
		"currency": transaction_data.get("currencyCode"),
		"description": transaction_data.get("description", "")[:140],
		"reference_number": transaction_data.get("transactionId"),
		"transaction_id": transaction_data.get("transactionId"),
		# Custom fields ACube
		"acube_transaction_id": transaction_data.get("transactionId"),
		"api_source": "ACube",
		"acube_booking_date": parse_date(transaction_data.get("madeOn")),
		"acube_value_date": parse_date(transaction_data.get("madeOn")),
		"acube_status": transaction_data.get("status"),
		"acube_category": transaction_data.get("category"),
		"acube_raw_data": transaction_data
	})

	# Prova a estrarre info controparte dal campo extra
	extra = transaction_data.get("extra", {})
	if extra:
		# Cerca payer o payee
		if extra.get("payer"):
			bank_txn.bank_party_name = extra.get("payer")[:140]
		elif extra.get("payee"):
			bank_txn.bank_party_name = extra.get("payee")[:140]

	bank_txn.insert(ignore_permissions=True)
	return bank_txn
