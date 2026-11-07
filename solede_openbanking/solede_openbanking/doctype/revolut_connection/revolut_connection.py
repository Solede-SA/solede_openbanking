# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RevolutConnection(Document):
	def validate(self):
		if self.private_key:
			pk = self.get_password("private_key", raise_exception=False)
			if pk and "BEGIN" not in pk:
				frappe.throw(_("Private Key non valida: il formato deve essere PEM (deve contenere 'BEGIN ... PRIVATE KEY')."))

		if not self.redirect_uri.startswith(("http://", "https://")):
			frappe.throw(_("Redirect URI deve iniziare con http:// o https://."))

		# Il consenso dato vale per i permessi di allora: cambiati i permessi, va rifatto.
		if not self.is_new() and self.has_value_changed("permessi") and self.connection_status == "Connected":
			self.connection_status = "Needs Reauth"
