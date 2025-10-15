# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import re
import json
from datetime import datetime
from frappe import _
from solede_openbanking.api.client import ACubeAPIClient


def format_currency(amount, currency="EUR"):
    """
    Formatta un importo come valuta in formato italiano.

    Args:
        amount: Importo da formattare (numero o stringa)
        currency: Codice valuta (default: EUR)

    Returns:
        Stringa formattata (es. "1.234,56 EUR")
    """
    if amount is None:
        return "N/A"

    try:
        amount_float = float(amount)
        # Formato italiano: 1.234,56 €
        formatted = f"{amount_float:,.2f} {currency}".replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    except (ValueError, TypeError):
        return str(amount)


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


def format_datetime_display(iso_string):
    """
    Converte una stringa datetime ISO 8601 in formato leggibile usando frappe.utils.

    Args:
        iso_string: Stringa in formato ISO 8601 (es. "2026-01-11T14:51:05Z")

    Returns:
        Stringa formattata secondo le impostazioni dell'utente
    """
    if not iso_string:
        return "N/A"

    try:
        # Converte in formato MySQL usando la funzione esistente
        mysql_datetime = parse_iso_datetime(iso_string)
        if not mysql_datetime:
            return "N/A"

        # Usa frappe.utils.format_datetime per formattare secondo le preferenze dell'utente
        return frappe.utils.format_datetime(mysql_datetime)
    except Exception as e:
        frappe.log_error(f"Error formatting datetime: {iso_string}, Error: {str(e)}", "DateTime Format Error")
        return "N/A"


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
    client = ACubeAPIClient(company)

    if not client.company_doc.company_name:
        frappe.throw(_("Company name not found in Company {0}").format(company))

    if not client.settings.email:
        frappe.throw(_("Email not configured in OpenBanking Settings"))

    # Prepara il payload per creare il Business Registry
    payload = {
        "fiscalId": client.fiscal_id,
        "businessName": client.company_doc.company_name,
        "email": client.settings.email,
        "emailAlerts": True,
        "locale": "it",
        "country": "IT",
        "enabled": True
    }

    # Effettua la richiesta
    response_data = client.post(
        "business-registry",
        "Create Business Registry",
        payload=payload,
        expected_status_codes=[201]
    )

    # Segna il Business Registry come creato
    client.settings.business_registry_created = 1
    client.settings.save(ignore_permissions=True)
    frappe.db.commit()

    print(f"DEBUG - Business Registry marked as created")

    return {
        "success": True,
        "message": _("Business Registry created successfully"),
        "data": response_data
    }


@frappe.whitelist()
def get_business_registry_info(company):
    """
    Recupera le informazioni del Business Registry per l'azienda specificata.

    Args:
        company: Nome della company
    """
    client = ACubeAPIClient(company)

    try:
        response_data = client.get(
            f"business-registry/{client.fiscal_id}",
            "Get Business Registry Info"
        )

        return {
            "success": True,
            "data": response_data
        }
    except Exception as e:
        if "404" in str(e):
            frappe.throw(_("Business Registry not found. Please create it first."))
        raise


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
    client = ACubeAPIClient(company)

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

    response_data = client.post(
        f"business-registry/{client.fiscal_id}/connect",
        "Start Connect Request",
        payload=payload,
        expected_status_codes=[201]
    )

    connect_url = response_data.get("connectUrl")
    if not connect_url:
        frappe.throw(_("Connect URL not found in response"))

    return {
        "success": True,
        "connect_url": connect_url,
        "message": _("Connect request created successfully")
    }


@frappe.whitelist()
def get_accounts(company):
    """
    Recupera tutti gli account bancari autorizzati per il Business Registry.
    Aggiorna la child table degli account nel documento OpenBanking Settings.

    Args:
        company: Nome della company
    """
    client = ACubeAPIClient(company)

    try:
        accounts_data = client.get(
            f"business-registry/{client.fiscal_id}/accounts",
            "Get Accounts"
        )

        # Pulisci la tabella esistente
        client.settings.accounts = []

        # Aggiungi gli account alla child table
        # Salviamo uuid, iban, enabled, raw_data e i campi display formattati
        for account in accounts_data:
            client.settings.append("accounts", {
                "uuid": account.get("uuid"),
                "iban": account.get("iban"),
                "bank_display": account.get("providerName"),
                "balance_display": format_currency(account.get("balance"), account.get("currencyCode", "EUR")),
                "consent_expires_display": format_datetime_display(account.get("consentExpiresAt")),
                "enabled": 1 if account.get("enabled") else 0,
                "raw_data": json.dumps(account, indent=2)
            })

        # Salva il documento
        client.settings.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "success": True,
            "message": _("Retrieved {0} accounts").format(len(accounts_data)),
            "count": len(accounts_data)
        }
    except Exception as e:
        if "404" in str(e):
            frappe.throw(_("No accounts found. Please connect a bank account first."))
        raise


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
    client = ACubeAPIClient(company)

    payload = {"enabled": bool(int(enabled))}

    response_data = client.put(
        f"accounts/{uuid}",
        "Toggle Account",
        payload=payload
    )

    # Aggiorna direttamente il campo enabled nella child table usando db.set_value
    # Questo evita conflitti di concorrenza quando si abilitano/disabilitano più account rapidamente
    for account in client.settings.accounts:
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


@frappe.whitelist()
def delete_account(company, uuid):
    """
    Elimina un account bancario e tutti gli account associati alla stessa connessione bancaria.
    Tutti gli account devono essere disabilitati e non avere pagamenti collegati.

    Args:
        company: Nome della company
        uuid: UUID dell'account da eliminare
    """
    client = ACubeAPIClient(company)

    response_data = client.delete(
        f"accounts/{uuid}",
        "Delete Account",
        expected_status_codes=[202]
    )

    removed_accounts = response_data.get("removedAccounts", [])

    # Rimuovi gli account dalla child table
    accounts_to_keep = []
    for account in client.settings.accounts:
        if account.uuid not in removed_accounts:
            accounts_to_keep.append(account)

    client.settings.accounts = []
    for account in accounts_to_keep:
        client.settings.append("accounts", account.as_dict())

    client.settings.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "message": _("Account deleted successfully. {0} account(s) removed.").format(len(removed_accounts)),
        "removed_accounts": removed_accounts
    }


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
	client = ACubeAPIClient(company)

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

	try:
		transactions_data = client.get(
			f"business-registry/{client.fiscal_id}/transactions",
			"Get Transactions",
			params=params
		)

		return {
			"success": True,
			"transactions": transactions_data,
			"total": len(transactions_data),
			"page": page,
			"items_per_page": items_per_page
		}
	except Exception as e:
		if "404" in str(e):
			# Nessuna transazione trovata
			return {
				"success": True,
				"transactions": [],
				"total": 0,
				"page": page,
				"items_per_page": items_per_page
			}
		raise


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

	# Contatori dettagliati per i skip
	skip_reasons = {
		"already_imported": 0,
		"currency_not_found": 0,
		"currency_mismatch": 0
	}

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
				log_entry = None
				try:
					transaction_id = txn.get("transactionId")
					transaction_currency = txn.get("currencyCode")

					# 1. Controlla se esiste già il Bank Transaction
					existing_bank_txn = frappe.db.exists(
						"Bank Transaction",
						{"acube_transaction_id": transaction_id}
					)

					if existing_bank_txn:
						print(f"DEBUG - Transaction {transaction_id} already exists in Bank Transaction, skipping")
						skipped_count += 1
						skip_reasons["already_imported"] += 1
						continue

					# 2. Controlla se esiste già il log
					existing_log = frappe.db.exists(
						"ACube Transaction Log",
						{"acube_transaction_id": transaction_id}
					)

					if existing_log:
						print(f"DEBUG - Transaction {transaction_id} already exists in ACube Transaction Log, skipping")
						skipped_count += 1
						skip_reasons["already_imported"] += 1
						continue

					# 3. Verifica che la valuta esista in ERPNext
					if not frappe.db.exists("Currency", transaction_currency):
						print(f"WARNING - Currency {transaction_currency} not configured in ERPNext, skipping transaction {transaction_id}")
						skipped_count += 1
						skip_reasons["currency_not_found"] += 1
						continue

					# 4. Ottieni la valuta del Bank Account tramite il Company Account collegato
					if bank_account:
						company_account = frappe.db.get_value("Bank Account", bank_account, "account")
						if company_account:
							bank_account_currency = frappe.db.get_value("Account", company_account, "account_currency")

							if bank_account_currency and transaction_currency != bank_account_currency:
								print(f"WARNING - Transaction {transaction_id} currency {transaction_currency} does not match Bank Account currency {bank_account_currency}, skipping")
								skipped_count += 1
								skip_reasons["currency_mismatch"] += 1
								continue

					# 5. Crea il log della transazione
					log_entry = create_transaction_log(
						company=company,
						account_uuid=acc_uuid,
						transaction_data=txn,
						bank_account=bank_account
					)

					# Crea Bank Transaction
					bank_txn = create_bank_transaction_from_acube(
						company=company,
						bank_account=bank_account,
						account_info=account_info,
						transaction_data=txn,
						transaction_log=log_entry.name
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

	# Costruisci messaggio dettagliato
	message_parts = [_("Import completed: {0} imported, {1} skipped, {2} failed").format(
		imported_count, skipped_count, failed_count
	)]

	# Aggiungi dettagli skip se ci sono transazioni skippate
	if skipped_count > 0:
		skip_details = []
		if skip_reasons["already_imported"] > 0:
			skip_details.append(_("{0} already imported").format(skip_reasons["already_imported"]))
		if skip_reasons["currency_not_found"] > 0:
			skip_details.append(_("{0} currency not found").format(skip_reasons["currency_not_found"]))
		if skip_reasons["currency_mismatch"] > 0:
			skip_details.append(_("{0} currency mismatch").format(skip_reasons["currency_mismatch"]))

		if skip_details:
			message_parts.append("<br><br>" + _("Skip reasons:") + "<br>- " + "<br>- ".join(skip_details))

	message = "".join(message_parts)

	return {
		"success": True,
		"imported": imported_count,
		"skipped": skipped_count,
		"failed": failed_count,
		"message": message,
		"skip_reasons": skip_reasons
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
		"raw_data": json.dumps(transaction_data, indent=2)
	})
	log.insert(ignore_permissions=True)
	return log


def create_bank_transaction_from_acube(company, bank_account, account_info, transaction_data, transaction_log=None):
	"""
	Crea un Bank Transaction da dati ACube.

	Args:
		company: Company
		bank_account: Bank Account ERPNext
		account_info: Info account dalla child table
		transaction_data: Dati transazione da API
		transaction_log: Nome del documento ACube Transaction Log (opzionale)

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
		"acube_transaction_log": transaction_log,
		"acube_transaction_id": transaction_data.get("transactionId"),
		"api_source": "ACube",
		"acube_booking_date": parse_date(transaction_data.get("madeOn")),
		"acube_value_date": parse_date(transaction_data.get("madeOn")),
		"acube_status": transaction_data.get("status"),
		"acube_category": transaction_data.get("category"),
		"acube_raw_data": json.dumps(transaction_data, indent=2)
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
	bank_txn.submit()
	return bank_txn


@frappe.whitelist()
def cancel_duplicate_transaction(bank_transaction):
	"""
	Annulla una Bank Transaction duplicata importata da ACube.
	La Bank Transaction viene cancellata (docstatus=2) rimanendo visibile con stato "Cancelled".
	Non può più essere riconciliata. Il log ACube viene aggiornato come "Duplicate".

	Args:
		bank_transaction: Nome del documento Bank Transaction da annullare

	Returns:
		dict: {"success": True, "message": "..."}
	"""
	# Ottieni il documento Bank Transaction
	bank_txn = frappe.get_doc("Bank Transaction", bank_transaction)

	# Verifica che provenga da ACube
	if bank_txn.api_source != "ACube":
		frappe.throw(_("Solo le transazioni importate da ACube possono essere annullate con questa funzione"))

	# Verifica che sia submitted
	if bank_txn.docstatus != 1:
		frappe.throw(_("Solo le transazioni submitted possono essere annullate"))

	# Verifica che non sia già riconciliata
	if bank_txn.status == "Reconciled":
		frappe.throw(_("Non è possibile annullare una transazione già riconciliata"))

	# Ottieni il Transaction Log collegato
	transaction_log_name = bank_txn.acube_transaction_log

	try:
		# Cancel la Bank Transaction (docstatus diventa 2 = Cancelled)
		# Questo la rimuove automaticamente dalla riconciliazione
		bank_txn.cancel()
		frappe.logger().info(f"Bank Transaction {bank_transaction} cancelled as duplicate")

		# Aggiorna il Transaction Log se esiste
		if transaction_log_name:
			frappe.db.set_value("ACube Transaction Log", transaction_log_name, {
				"import_status": "Duplicate",
				"error_message": "Transazione annullata manualmente come duplicato"
			})
			frappe.logger().info(f"ACube Transaction Log {transaction_log_name} marked as duplicate")

		frappe.db.commit()

		return {
			"success": True,
			"message": _("Transazione annullata come duplicato. Rimane visibile con stato Cancelled e non può più essere riconciliata.")
		}

	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.log_error(f"Error cancelling transaction {bank_transaction}: {error_msg}", "Cancel Transaction Error")
		frappe.throw(_("Errore durante l'annullamento della transazione: {0}").format(error_msg))
