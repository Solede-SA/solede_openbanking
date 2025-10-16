# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def get_context(context):
	"""
	Pagina di callback per il ritorno dal flusso di pagamento Open Banking.
	"""
	# Verifica autenticazione
	if frappe.session.user == "Guest":
		frappe.throw(_("Devi essere autenticato per accedere a questa pagina"))

	# Ottieni parametri dalla query string
	payment_uuid = frappe.form_dict.get("payment_uuid")

	if not payment_uuid:
		context.error = True
		context.title = _("Errore")
		context.message = _("Payment UUID non fornito")
		return context

	# Recupera OpenBanking Payment
	payment_name = frappe.db.get_value("OpenBanking Payment", {"uuid": payment_uuid}, "name")

	if not payment_name:
		context.error = True
		context.title = _("Errore")
		context.message = _("Pagamento non trovato")
		return context

	try:
		payment_doc = frappe.get_doc("OpenBanking Payment", payment_name)

		# Verifica permessi
		if not frappe.has_permission("OpenBanking Payment", "read", payment_doc):
			frappe.throw(_("Non hai i permessi per visualizzare questo pagamento"))

		context.payment = payment_doc
		context.title = _("Pagamento in elaborazione")

		# Determina messaggio e stato in base allo status
		if payment_doc.status == "completed":
			context.success = True
			context.message = _("Il pagamento è stato completato con successo!")
			context.icon = "check-circle"
			context.color = "green"
		elif payment_doc.status == "failed":
			context.error = True
			context.message = _("Il pagamento è fallito")
			context.icon = "times-circle"
			context.color = "red"
			if payment_doc.error_message:
				context.error_detail = payment_doc.error_message
		elif payment_doc.status == "pending":
			context.warning = True
			context.message = _("Il pagamento è in attesa di autorizzazione")
			context.icon = "clock"
			context.color = "orange"
		elif payment_doc.status == "processing":
			context.info = True
			context.message = _("Il pagamento è in elaborazione")
			context.icon = "spinner"
			context.color = "blue"
		else:
			context.warning = True
			context.message = _("Status pagamento: {0}").format(payment_doc.status)
			context.icon = "info-circle"
			context.color = "gray"

		# Link al documento di riferimento
		if payment_doc.reference_doctype and payment_doc.reference_name:
			context.reference_doctype = payment_doc.reference_doctype
			context.reference_name = payment_doc.reference_name
			context.reference_link = frappe.utils.get_url_to_form(
				payment_doc.reference_doctype,
				payment_doc.reference_name
			)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Payment Callback Error")
		context.error = True
		context.title = _("Errore")
		context.message = str(e)

	return context
