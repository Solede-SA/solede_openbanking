"""I movimenti che una regola riconosce si registrano da soli: le spese bancarie (commissioni, canoni, bolli) e gli
acconti ai fornitori pagati prima della fattura (addebiti della carta a ogni soglia di spesa). Li riconosce una regola
dei movimenti bancari di ERPNext (Bank Transaction Rule): «Bank Entry» a conto unico dice il conto della spesa,
«Payment Entry» dice a chi va il pagamento e su quale conto, e il pagamento resta non allocato finché la fattura non
arriva e lo usa. La regola è la decisione di Lorenzo, qui si esegue soltanto. Vale per tutti i movimenti della società,
da qualunque fonte arrivino (ACube, il collegamento diretto a Revolut). La registrazione va nel giorno di addebito e
resta collegata al movimento. Le regole di altro tipo restano suggerimenti nello strumento di riconciliazione di ERPNext."""

import frappe
from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
	create_bank_entry_and_reconcile,
	create_payment_entry_and_reconcile,
)
from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import _run_rule_evaluation
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import flt

from solede_openbanking.api.business_registry import addebito_del_movimento

TOLLERANZA = 0.01
PAGAMENTO = "Payment Entry"


def registra(company):
	"""Ogni movimento importato e non riconciliato che ricade in una di queste regole. Uno che non si riesce a registrare
	va nell'Error Log col suo nome, non ferma gli altri e perde la regola: non si riprova ogni ora, resta da abbinare."""
	regole = {
		r.name: r
		for r in frappe.get_all(
			"Bank Transaction Rule",
			filters={"company": company, "classify_as": ["in", ("Bank Entry", PAGAMENTO)]},
			fields=["name", "classify_as", "bank_entry_type", "account", "party_type", "party"],
		)
		if r.classify_as == PAGAMENTO or r.bank_entry_type != "Multiple Accounts"
	}
	if not regole:
		return
	_run_rule_evaluation()
	for bt in frappe.get_all(
		"Bank Transaction",
		filters={"company": company, "docstatus": 1, "status": "Unreconciled", "matched_transaction_rule": ["in", list(regole)]},
		fields=["name", "company", "bank_account", "withdrawal", "unallocated_amount", "date", "api_source", "acube_booking_date", "reference_number", "description", "matched_transaction_rule"],
	):
		frappe.db.savepoint("regola_movimento")
		try:
			_registra(bt, regole[bt.matched_transaction_rule])
		except Exception:
			frappe.db.rollback(save_point="regola_movimento")
			frappe.log_error(title=f"Movimento non registrato dalla regola: {bt.name}")
			frappe.db.set_value("Bank Transaction", bt.name, "matched_transaction_rule", None)
		frappe.db.commit()


def _registra(bt, regola):
	banca = frappe.get_cached_value("Bank Account", bt.bank_account, "account")
	importo = bt.unallocated_amount
	uscita, entrata = (importo, 0) if bt.withdrawal else (0, importo)
	giorno = addebito_del_movimento(bt)
	numero = (bt.reference_number or bt.description)[:140]  # il numero del movimento; senza (inserito a mano), la descrizione
	if regola.classify_as == PAGAMENTO:
		create_payment_entry_and_reconcile(bt.name, {
			"payment_type": "Pay" if uscita else "Receive",
			"company": bt.company,
			"party_type": regola.party_type,
			"party": regola.party,
			"paid_from": banca if uscita else regola.account,
			"paid_to": regola.account if uscita else banca,
			"paid_amount": importo,
			"received_amount": importo,
			"posting_date": giorno,
			"reference_no": numero,
			"reference_date": giorno,
		})
		return
	create_bank_entry_and_reconcile(
		bank_transaction_name=bt.name,
		cheque_date=giorno,
		posting_date=giorno,
		cheque_no=numero,
		user_remark=bt.description,
		entries=[
			{"account": banca, "bank_account": bt.bank_account, "debit": entrata, "credit": uscita},
			{"account": regola.account, "debit": uscita, "credit": entrata},
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
