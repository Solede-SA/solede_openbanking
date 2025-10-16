# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _


# Configurazione API - Aggiungi le tue API key nelle Openbanking Settings
IBAN_API_PROVIDERS = {
	"iban.com": {
		"url": "https://api.iban.com/clients/api/v4/iban/{iban}",
		"method": "GET",
		"auth_param": "api_key",
		"parser": "parse_iban_com_response"
	},
	"ibanapi.com": {
		"url": "https://api.ibanapi.com/v1/validate/{iban}",
		"method": "GET",
		"auth_param": "api_key",
		"parser": "parse_ibanapi_com_response"
	},
	"api-ninjas": {
		"url": "https://api.api-ninjas.com/v1/iban",
		"method": "GET",
		"auth_header": "X-Api-Key",
		"param": "iban",
		"parser": "parse_api_ninjas_response"
	}
}


def enrich_iban(iban, company):
	"""
	Arricchisce l'IBAN con informazioni sulla banca usando API esterne
	Ritorna: dict con bank_name, swift_number, country_code
	"""
	if not iban:
		frappe.throw(_("IBAN è richiesto"))

	if not company:
		frappe.throw(_("Company è richiesta"))

	# Rimuovi spazi e converti in maiuscolo
	iban_clean = iban.replace(" ", "").upper()

	# Validazione base formato IBAN
	if not validate_iban_format(iban_clean):
		frappe.throw(_("Formato IBAN non valido"))

	# Ottieni configurazione API dal DocType Openbanking Settings
	api_provider, api_key = get_iban_api_config(company)

	# Chiama l'API configurata
	result = call_iban_api(iban_clean, api_provider, api_key)

	if not result or not result.get("bank_name"):
		frappe.throw(_("API non ha restituito informazioni sulla banca per questo IBAN"))

	return result


def validate_iban_format(iban):
	"""Validazione formato IBAN con algoritmo mod-97"""
	if len(iban) < 15 or len(iban) > 34:
		return False

	# Sposta i primi 4 caratteri alla fine
	rearranged = iban[4:] + iban[:4]

	# Converti lettere in numeri (A=10, B=11, ..., Z=35)
	numeric_iban = ""
	for char in rearranged:
		if char.isalpha():
			numeric_iban += str(ord(char) - ord('A') + 10)
		else:
			numeric_iban += char

	# Verifica mod 97 = 1
	try:
		return int(numeric_iban) % 97 == 1
	except ValueError:
		return False


def get_iban_api_config(company):
	"""Ottiene configurazione API IBAN dalle OpenBanking Settings per la company specificata"""
	if not company:
		frappe.throw(_("Company è richiesta per ottenere la configurazione API IBAN"))

	if not frappe.db.exists("OpenBanking Settings", company):
		frappe.throw(_("OpenBanking Settings non trovato per la company: {0}").format(company))

	settings = frappe.get_doc("OpenBanking Settings", company)
	api_provider = settings.get("iban_api_provider")
	# Usa get_password per decifrare il campo Password
	api_key = settings.get_password("iban_api_key")

	if not api_provider or not api_key:
		frappe.throw(_(
			"Configurazione API IBAN mancante per la company {0}. "
			"Vai in OpenBanking Settings ({0}) e configura IBAN API Provider e IBAN API Key."
		).format(company))

	return api_provider, api_key


def call_iban_api(iban, provider, api_key):
	"""Chiama l'API IBAN configurata"""
	if provider not in IBAN_API_PROVIDERS:
		frappe.throw(_("Provider API non supportato: {0}").format(provider))

	config = IBAN_API_PROVIDERS[provider]

	# Prepara URL
	if "{iban}" in config["url"]:
		url = config["url"].format(iban=iban)
	else:
		url = config["url"]

	# Prepara parametri
	params = {}
	if "param" in config:
		params[config["param"]] = iban
	if "auth_param" in config:
		params[config["auth_param"]] = api_key

	# Prepara headers
	headers = {"Accept": "application/json"}
	if "auth_header" in config:
		headers[config["auth_header"]] = api_key

	# Chiama API
	response = requests.get(url, params=params, headers=headers, timeout=15)

	if response.status_code != 200:
		frappe.throw(_(
			"Errore API {0}: Status {1} - {2}"
		).format(provider, response.status_code, response.text[:200]))

	data = response.json()

	# Parsa risposta usando il parser specifico
	parser_func = globals().get(config["parser"])
	if parser_func:
		return parser_func(data, iban)
	else:
		frappe.throw(_("Parser non trovato per provider: {0}").format(provider))


def parse_iban_com_response(data, iban):
	"""Parsa risposta da IBAN.com API"""
	if data.get("result") != 200:
		frappe.throw(_("IBAN non valido o non trovato"))

	iban_data = data.get("data", {})

	return {
		"bank_name": iban_data.get("bank"),
		"swift_number": iban_data.get("bic"),
		"country_code": iban_data.get("country_iso"),
		"bank_code": iban_data.get("bank_code"),
		"branch_code": iban_data.get("branch_code"),
		"city": iban_data.get("city"),
		"address": iban_data.get("address")
	}


def parse_ibanapi_com_response(data, iban):
	"""Parsa risposta da IBANapi.com API"""
	if data.get("result") != 200:
		message = data.get("message", "IBAN non valido")
		frappe.throw(_("IBAN non valido: {0}").format(message))

	# Estrai dati dalla struttura annidata
	iban_data = data.get("data", {})
	bank_data = iban_data.get("bank", {})

	return {
		"bank_name": bank_data.get("bank_name"),
		"swift_number": bank_data.get("bic"),
		"country_code": iban_data.get("country_code"),
		"bank_code": None,  # Non disponibile in questa API
		"branch_code": None,  # Non disponibile in questa API
		"city": bank_data.get("city"),
		"address": bank_data.get("address"),
		"zip": bank_data.get("zip")
	}


def parse_api_ninjas_response(data, iban):
	"""Parsa risposta da API Ninjas"""
	if not data.get("valid"):
		frappe.throw(_("IBAN non valido"))

	return {
		"bank_name": data.get("bank_name"),
		"swift_number": data.get("bic"),
		"country_code": data.get("country"),
		"bank_code": data.get("bank_code")
	}


@frappe.whitelist()
def create_bank_and_account_from_iban(iban, party_type, party, account_name=None):
	"""
	Crea automaticamente Bank e Bank Account dall'IBAN
	"""
	# Rimuovi spazi
	iban_clean = iban.replace(" ", "").upper()

	# VERIFICA SUBITO se Bank Account esiste già per questo fornitore
	existing_account = frappe.db.exists(
		"Bank Account",
		{
			"iban": iban_clean,
			"party_type": party_type,
			"party": party
		}
	)

	if existing_account:
		account_doc = frappe.get_doc("Bank Account", existing_account)
		frappe.msgprint(
			_("Bank Account già esistente per questo {0}: {1}").format(
				party_type,
				frappe.bold(account_doc.name)
			),
			indicator="orange",
			alert=True
		)
		return account_doc

	# Se non esiste, procedi con validazione e creazione
	# Ottieni la company dal fornitore/cliente
	party_doc = frappe.get_doc(party_type, party)

	# Per Supplier, usa il campo default_company se esiste, altrimenti usa la prima company disponibile
	if party_type == "Supplier":
		company = frappe.defaults.get_user_default("Company")
		if not company:
			company = frappe.get_all("Company", limit=1, pluck="name")
			if company:
				company = company[0]
	else:
		company = party_doc.get("company")

	if not company:
		frappe.throw(_("Impossibile determinare la company per {0}").format(party))

	# Arricchisci IBAN con la company (SOLO se non esiste già)
	bank_info = enrich_iban(iban_clean, company)

	# 1. Crea o ottieni Bank
	bank = get_or_create_bank(bank_info)

	# 3. Crea Bank Account
	if not account_name:
		party_name = party_doc.supplier_name if party_type == "Supplier" else party_doc.customer_name
		account_name = f"{party_name} - {bank_info['bank_name']}"

	bank_account = frappe.get_doc({
		"doctype": "Bank Account",
		"account_name": account_name,
		"bank": bank.name,
		"iban": iban_clean,
		"bank_account_no": extract_account_number(iban_clean),
		"branch_code": bank_info.get("branch_code"),
		"party_type": party_type,
		"party": party,
		"is_company_account": 0,
		"is_default": 1
	})

	bank_account.insert()
	frappe.db.commit()

	frappe.msgprint(_("Bank Account creato con successo: {0}").format(bank_account.name))

	return bank_account


def extract_account_number(iban):
	"""Estrae il numero di conto dall'IBAN"""
	if iban.startswith("IT"):
		# Per Italia, il numero di conto è dalla posizione 15 in poi
		return iban[15:]
	else:
		# Per altri paesi, prendi tutto dopo i primi 4 caratteri
		return iban[4:]


def get_or_create_bank(bank_info):
	"""Crea Bank se non esiste"""
	bank_name = bank_info.get("bank_name")
	swift_number = bank_info.get("swift_number")

	if not bank_name:
		frappe.throw(_("Nome banca non disponibile"))

	# Cerca per nome
	existing_bank = frappe.db.exists("Bank", {"bank_name": bank_name})

	if existing_bank:
		return frappe.get_doc("Bank", existing_bank)

	# Cerca per SWIFT se disponibile
	if swift_number:
		existing_bank = frappe.db.exists("Bank", {"swift_number": swift_number})
		if existing_bank:
			return frappe.get_doc("Bank", existing_bank)

	# Crea nuovo Bank
	bank = frappe.get_doc({
		"doctype": "Bank",
		"bank_name": bank_name,
		"swift_number": swift_number
	})

	bank.insert()
	frappe.db.commit()

	return bank


@frappe.whitelist()
def validate_iban_api(iban, company=None):
	"""API per validare un IBAN dal client"""
	try:
		iban_clean = iban.replace(" ", "").upper()
		is_valid = validate_iban_format(iban_clean)

		if not is_valid:
			return {
				"valid": False,
				"message": _("IBAN non valido")
			}

		# Se company non è specificata, usa quella di default dell'utente
		if not company:
			company = frappe.defaults.get_user_default("Company")

		if not company:
			return {
				"valid": False,
				"message": _("Company non specificata. Impossibile validare IBAN.")
			}

		bank_info = enrich_iban(iban_clean, company)
		return {
			"valid": True,
			"bank_info": bank_info
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "IBAN Validation Error")
		return {
			"valid": False,
			"message": str(e)
		}
