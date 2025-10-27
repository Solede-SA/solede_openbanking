# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OpenBankingPayment(Document):
	"""DocType per tracciare i pagamenti Open Banking"""

	def validate(self):
		"""Validazioni prima del salvataggio"""
		if self.amount and self.amount <= 0:
			frappe.throw("Amount must be greater than 0")

		if self.system == "sepa-instant" and self.amount > 100000:
			frappe.throw("SEPA Instant payments cannot exceed 100,000 EUR")

	def on_update(self):
		"""Aggiorna il documento di riferimento quando cambia lo status"""
		if self.has_value_changed("status") and self.reference_doctype and self.reference_name:
			self.update_reference_document()

	def update_reference_document(self):
		"""Aggiorna il documento di riferimento con lo status del pagamento"""
		if not frappe.db.exists(self.reference_doctype, self.reference_name):
			return

		try:
			ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)

			# Aggiorna custom field se esiste
			if hasattr(ref_doc, "openbanking_payment"):
				ref_doc.db_set("openbanking_payment", self.name, update_modified=False)

			if hasattr(ref_doc, "openbanking_status"):
				ref_doc.db_set("openbanking_status", self.status, update_modified=False)

		except Exception as e:
			frappe.log_error(f"Error updating reference document: {e!s}", "OpenBanking Payment Update Error")
