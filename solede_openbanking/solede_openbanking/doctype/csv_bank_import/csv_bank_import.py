# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils.file_manager import save_file

from solede_openbanking.solede_openbanking.parsers import get_parser


class CSVBankImport(Document):
	@frappe.whitelist()
	def parse_file(self):
		if not self.csv_file:
			frappe.throw(_("Carica un file CSV prima di procedere"))
		if not self.format:
			frappe.throw(_("Seleziona il formato del file"))

		file_doc = frappe.get_doc("File", {"file_url": self.csv_file})
		parser = get_parser(self.format)
		raw_lines = parser.parse(file_doc.get_full_path())

		existing = _lookup_existing_bank_transactions([ln["transaction_id"] for ln in raw_lines], self.bank_account)

		self.transactions = []
		total_credit = total_debit = already_imported = 0

		for ln in raw_lines:
			match = existing.get(ln["transaction_id"])
			self.append(
				"transactions",
				{
					"date": ln["date"],
					"transaction_id": ln["transaction_id"],
					"description": ln["description"],
					"deposit": ln["deposit"],
					"withdrawal": ln["withdrawal"],
					"included_fee": ln["included_fee"],
					"currency": ln["currency"],
					"transaction_type": ln["transaction_type"],
					"payer": ln["payer"],
					"solede_orig_currency": ln.get("solede_orig_currency"),
					"solede_orig_amount": ln.get("solede_orig_amount") or 0,
					"solede_beneficiary_iban": ln.get("solede_beneficiary_iban"),
					"status": "Already Imported" if match else "Pending",
					"bank_transaction": match,
				},
			)
			total_credit += flt(ln["deposit"])
			total_debit += flt(ln["withdrawal"])
			if match:
				already_imported += 1

		if raw_lines:
			self.from_date = min(ln["date"] for ln in raw_lines)
			self.to_date = max(ln["date"] for ln in raw_lines)

		self.total_transactions = len(raw_lines)
		self.total_credit = total_credit
		self.total_debit = total_debit
		self.status = "Parsed"
		self.save()

		msg = _("File parsato: {0} transazioni trovate.").format(len(raw_lines))
		if already_imported:
			msg += "<br>" + _("{0} già presenti in Bank Transaction (verranno saltate).").format(
				already_imported
			)
		frappe.msgprint(msg, indicator="orange" if already_imported else "green", alert=True)

	@frappe.whitelist()
	def create_bank_transactions(self):
		if not self.bank_account:
			frappe.throw(_("Seleziona un Bank Account"))
		if not self.transactions:
			frappe.throw(_("Nessuna transazione. Parsa il file prima."))

		company = frappe.db.get_value("Bank Account", self.bank_account, "company")
		created = skipped = 0

		for line in self.transactions:
			if line.status in ("Created", "Already Imported", "Skipped"):
				skipped += 1
				continue

			bt_name = insert_bank_transaction(
				self.bank_account,
				company,
				{
					"date": line.date,
					"transaction_id": line.transaction_id,
					"description": line.description,
					"deposit": line.deposit,
					"withdrawal": line.withdrawal,
					"included_fee": line.included_fee,
					"currency": line.currency,
					"transaction_type": line.transaction_type,
					"payer": line.payer,
					"solede_orig_currency": line.solede_orig_currency,
					"solede_orig_amount": line.solede_orig_amount,
					"solede_beneficiary_iban": line.solede_beneficiary_iban,
				},
			)
			line.bank_transaction = bt_name
			line.status = "Created"
			created += 1

		self.created_count = created
		self.skipped_count = skipped
		self.status = "Processed"
		self.save()

		frappe.msgprint(
			_("Create {0} Bank Transaction, saltate {1}").format(created, skipped),
			indicator="green",
			alert=True,
		)


def _lookup_existing_bank_transactions(transaction_ids, bank_account):
	"""Stessa chiave di idempotenza del sync API: un cambio tra conti propri ha lo stesso id su due conti."""
	if not transaction_ids:
		return {}
	rows = frappe.get_all(
		"Bank Transaction",
		filters={"transaction_id": ["in", transaction_ids], "bank_account": bank_account, "docstatus": ["!=", 2]},
		fields=["transaction_id", "name"],
	)
	return {r.transaction_id: r.name for r in rows}


def insert_bank_transaction(
	bank_account: str,
	company: str,
	normalized: dict,
	*,
	ignore_permissions: bool = False,
) -> str:
	"""Crea (e submit) una Bank Transaction dal dict normalizzato.

	Pattern condiviso tra import CSV e sync API. `normalized` segue lo schema definito
	in `BankCSVParser.parse()` (date, transaction_id, description, deposit, withdrawal,
	included_fee, currency, transaction_type, payer, solede_*).
	"""
	balance_after = normalized.get("revolut_balance_after")
	bt = frappe.get_doc(
		{
			"doctype": "Bank Transaction",
			"date": normalized["date"],
			"bank_account": bank_account,
			"company": company,
			"currency": normalized["currency"],
			"deposit": flt(normalized.get("deposit") or 0),
			"withdrawal": flt(normalized.get("withdrawal") or 0),
			"included_fee": flt(normalized.get("included_fee") or 0),
			"description": normalized.get("description"),
			"reference_number": (normalized.get("description") or "")[:140],
			"transaction_id": normalized["transaction_id"],
			"transaction_type": normalized.get("transaction_type"),
			"bank_party_name": normalized.get("payer"),
			"solede_orig_currency": normalized.get("solede_orig_currency"),
			"solede_orig_amount": flt(normalized.get("solede_orig_amount") or 0),
			"solede_beneficiary_iban": normalized.get("solede_beneficiary_iban"),
			"revolut_balance_after": flt(balance_after) if balance_after is not None else None,
			"revolut_completed_at": normalized.get("revolut_completed_at"),
			"revolut_in_sospeso": normalized.get("revolut_in_sospeso"),
			"status": "Pending",
		}
	)
	bt.insert(ignore_permissions=ignore_permissions)
	bt.submit()
	return bt.name


@frappe.whitelist()
def run_import(file_path, format, bank_account):
	with open(file_path, "rb") as f:
		content = f.read()

	file_doc = save_file(
		fname=file_path.rsplit("/", 1)[-1],
		content=content,
		dt="",
		dn="",
		is_private=1,
	)

	doc = frappe.get_doc(
		{
			"doctype": "CSV Bank Import",
			"csv_file": file_doc.file_url,
			"format": format,
			"bank_account": bank_account,
		}
	).insert(ignore_permissions=True)

	doc.parse_file()
	doc.create_bank_transactions()

	return {
		"docname": doc.name,
		"total": doc.total_transactions,
		"created": doc.created_count,
		"skipped": doc.skipped_count,
		"from_date": str(doc.from_date) if doc.from_date else None,
		"to_date": str(doc.to_date) if doc.to_date else None,
		"status": doc.status,
	}
