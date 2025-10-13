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
            error_log = f"Status: {status_code}, URL: {endpoint_url}, Detail: {detail}"
            frappe.log_error(error_log, "Business Registry Error")

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

            error_log = f"Status: {response.status_code}, URL: {endpoint_url}, Detail: {detail}"
            frappe.log_error(error_log, "Connect Request Error")
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

            error_log = f"Status: {response.status_code}, URL: {endpoint_url}, Detail: {detail}"
            frappe.log_error(error_log, "Get Accounts Error")
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

            # Aggiorna l'account nella child table
            for account in settings.accounts:
                if account.uuid == uuid:
                    account.enabled = int(enabled)
                    break

            settings.save(ignore_permissions=True)
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

            error_log = f"Status: {response.status_code}, URL: {endpoint_url}, Detail: {detail}"
            frappe.log_error(error_log, "Toggle Account Error")
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

            error_log = f"Status: {response.status_code}, URL: {endpoint_url}, Detail: {detail}"
            frappe.log_error(error_log, "Delete Account Error")
            frappe.throw(_("Failed to delete account (HTTP {0}): {1}").format(response.status_code, detail))

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        frappe.log_error(f"URL: {endpoint_url}, Error: {error_msg}", "Delete Account API Error")
        frappe.throw(_("Failed to connect to API: {0}").format(error_msg))
