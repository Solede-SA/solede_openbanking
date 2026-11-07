"""Le spese bancarie (commissioni, canoni, bolli) si registrano da sole. Le riconosce una regola dei movimenti bancari di
ERPNext (Bank Transaction Rule) di tipo «Bank Entry» a conto unico, che dice anche il conto: la regola è la decisione di
Lorenzo, qui si esegue soltanto. Vale per tutti i movimenti della società, da qualunque fonte arrivino (ACube, il
collegamento diretto a Revolut). La registrazione va nel giorno di addebito e resta collegata al movimento. Le regole di
altro tipo restano suggerimenti nello strumento di riconciliazione di ERPNext."""

import frappe
from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import create_bank_entry_and_reconcile
from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import _run_rule_evaluation


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
