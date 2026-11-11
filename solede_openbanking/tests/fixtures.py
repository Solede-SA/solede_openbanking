"""Dati di prova dei collegamenti bancari: conto Revolut, conto spese e impostazioni ACube della società, creati dal test
stesso (nessun dato vero richiesto). Idempotenti: i test fanno rollback e possono richiamarle."""

import frappe

COMPANY = "Solede SRL"
BANCA = "Revolut Ltd"
IBAN = "LT903250000000000001"
ACUBE_UUID = "acube-conto-di-prova"


def _conto(company, nome, **filtri):
	"""Conto di prova nello stesso gruppo di un conto esistente della società (`filtri`), qualunque sia il piano dei conti."""
	esistente = frappe.db.get_value("Account", {"company": company, "account_name": nome})
	if esistente:
		return esistente
	modello = frappe.db.get_value("Account", {"company": company, "is_group": 0, **filtri}, ["parent_account", "account_type"], as_dict=True)
	if not modello:
		frappe.throw(f"La società {company} non ha un conto {filtri} accanto a cui creare «{nome}»")
	return frappe.get_doc({
		"doctype": "Account", "account_name": nome, "company": company, "parent_account": modello.parent_account,
		"account_type": modello.account_type, "account_currency": "EUR",
	}).insert(ignore_permissions=True).name


def conto_revolut(company=COMPANY):
	"""Conto Revolut aziendale con IBAN e conto delle spese bancarie."""
	if not frappe.db.exists("Bank", BANCA):
		frappe.get_doc({"doctype": "Bank", "bank_name": BANCA}).insert(ignore_permissions=True)
	account = _conto(company, "Revolut EUR di prova", account_type="Bank")
	spese = _conto(company, "Spese bancarie di prova", root_type="Expense", account_type="")
	bank_account = frappe.db.get_value("Bank Account", {"account": account})
	if not bank_account:
		bank_account = frappe.get_doc({
			"doctype": "Bank Account", "account_name": "Revolut EUR di prova", "bank": BANCA, "company": company,
			"is_company_account": 1, "account": account, "iban": IBAN,
		}).insert(ignore_permissions=True).name
	return frappe._dict(bank_account=bank_account, account=account, spese=spese, iban=IBAN)


def acube(conto, company=COMPANY):
	"""Il conto di `conto_revolut` abilitato nelle impostazioni ACube della società (create se mancano): la riga del conto."""
	if frappe.db.exists("OpenBanking Settings", company):
		settings = frappe.get_doc("OpenBanking Settings", company)
	else:
		settings = frappe.get_doc({
			"doctype": "OpenBanking Settings", "company": company, "api_url": "https://acube.example.com",
			"openbanking_api_url": "https://ob.acube.example.com", "callback_base_url": "https://erp.example.com",
			"webhook_base_url": "https://erp.example.com", "email": "prova@example.com", "password": "prova",
			"payment_mode_of_payment": frappe.db.get_value("Mode of Payment", {}, "name"),
		})
	riga = next((r for r in settings.accounts if r.uuid == ACUBE_UUID), None)
	if not riga:
		riga = settings.append("accounts", {"uuid": ACUBE_UUID, "iban": conto.iban, "enabled": 1})
		settings.save(ignore_permissions=True)
	return riga
