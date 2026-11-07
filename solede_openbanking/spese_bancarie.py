"""Le spese bancarie (commissioni, canoni, bolli) si registrano da sole. Le riconosce una regola dei movimenti bancari di
ERPNext (Bank Transaction Rule) di tipo «Bank Entry» a conto unico, che dice anche il conto: la regola è la decisione di
Lorenzo, qui si esegue soltanto. Vale per tutti i movimenti della società, da qualunque fonte arrivino (ACube, il
collegamento diretto a Revolut). La registrazione va nel giorno di addebito e resta collegata al movimento. Le regole di
altro tipo restano suggerimenti nello strumento di riconciliazione di ERPNext."""

import frappe
from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
	create_bank_entry_and_reconcile,
)
from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import _run_rule_evaluation
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import flt

TOLLERANZA = 0.01


def registra(company):
	"""Ogni movimento importato e non riconciliato che ricade in una di queste regole. Uno che non si riesce a registrare
	va nell'Error Log col suo nome, non ferma gli altri e perde la regola: non si riprova ogni ora, resta da abbinare."""
	regole = dict(frappe.get_all(
		"Bank Transaction Rule",
		filters={"company": company, "classify_as": "Bank Entry", "bank_entry_type": ["!=", "Multiple Accounts"]},
		fields=["name", "account"],
		as_list=True,
	))
	if not regole:
		return
	_run_rule_evaluation()
	for bt in frappe.get_all(
		"Bank Transaction",
		filters={"company": company, "docstatus": 1, "status": "Unreconciled", "matched_transaction_rule": ["in", list(regole)]},
		fields=["name", "bank_account", "withdrawal", "unallocated_amount", "date", "api_source", "acube_booking_date", "reference_number", "description", "matched_transaction_rule"],
	):
		frappe.db.savepoint("spesa_bancaria")
		try:
			_registra(bt, regole[bt.matched_transaction_rule])
		except Exception:
			frappe.db.rollback(save_point="spesa_bancaria")
			frappe.log_error(title=f"Spesa bancaria non registrata: {bt.name}")
			frappe.db.set_value("Bank Transaction", bt.name, "matched_transaction_rule", None)
		frappe.db.commit()


def _registra(bt, conto):
	banca = frappe.get_cached_value("Bank Account", bt.bank_account, "account")
	importo = bt.unallocated_amount
	uscita, entrata = (importo, 0) if bt.withdrawal else (0, importo)
	# ACube dà la valuta nella data e il giorno di addebito a parte; per le altre fonti (Revolut diretto: il giorno in cui
	# il movimento è completato) la data è già il giorno di addebito.
	giorno = bt.acube_booking_date if bt.api_source == "ACube" else bt.date
	create_bank_entry_and_reconcile(
		bank_transaction_name=bt.name,
		cheque_date=giorno,
		posting_date=giorno,
		cheque_no=(bt.reference_number or bt.description)[:140],  # il numero del movimento; senza (inserito a mano), la descrizione
		user_remark=bt.description,
		entries=[
			{"account": banca, "bank_account": bt.bank_account, "debit": entrata, "credit": uscita},
			{"account": conto, "debit": uscita, "credit": entrata},
		],
	)


def registra_commissione_compresa(bt, conto):
	"""La commissione compresa in un movimento (`included_fee`, Revolut) diventa una spesa bancaria sul `conto`,
	collegata al movimento, che resta da abbinare per il netto. Una volta sola: se c'è già, non si rifà. Scrittura
	fatta qui e non con create_bank_entry_and_reconcile, che registra sempre tutto il residuo del movimento."""
	commissione = flt(bt.included_fee)
	if commissione <= 0 or any(
		p.payment_document == "Journal Entry" and abs(flt(p.allocated_amount) - commissione) <= TOLLERANZA for p in bt.payment_entries
	):
		return None
	banca, company = frappe.db.get_value("Bank Account", bt.bank_account, ["account", "company"])
	valuta = frappe.get_cached_value("Company", company, "default_currency")
	valuta_banca, valuta_spese = (frappe.get_cached_value("Account", conto_gl, "account_currency") for conto_gl in (banca, conto))
	cambio_banca = get_exchange_rate(valuta_banca, valuta, bt.date)
	if valuta_spese == valuta_banca:
		cambio_spese, importo_spese = cambio_banca, commissione
	else:
		cambio_spese = get_exchange_rate(valuta_spese, valuta, bt.date)
		importo_spese = flt(commissione * cambio_banca / cambio_spese, 2)
	scrittura = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Bank Entry",
		"company": company,
		"posting_date": bt.date,
		"cheque_no": bt.transaction_id,
		"cheque_date": bt.date,
		"multi_currency": 1,
		"user_remark": f"Commissione Revolut: {bt.description}",
		"accounts": [
			{"account": conto, "debit_in_account_currency": importo_spese, "exchange_rate": cambio_spese},
			{"account": banca, "credit_in_account_currency": commissione, "exchange_rate": cambio_banca},
		],
	}).insert()
	scrittura.submit()
	bt.add_payment_entries([{"payment_doctype": "Journal Entry", "payment_name": scrittura.name}])
	bt.save()
	return scrittura
