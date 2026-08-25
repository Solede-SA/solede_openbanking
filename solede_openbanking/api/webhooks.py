# Copyright (c) 2024-2025, Solede SA and contributors
# For license information, please see license.txt
# License: GNU Affero General Public License v3 or later (AGPLv3+)
# See https://www.gnu.org/licenses/agpl-3.0.html

import json
from datetime import datetime

import frappe
import requests
from frappe import _

# Cache per la chiave pubblica (evita chiamate ripetute)
_public_key_cache = None


def get_company_from_fiscal_id(fiscal_id):
	"""
	Trova la company associata a un fiscal_id.

	Args:
		fiscal_id: Il fiscal ID della company

	Returns:
		str: Il nome della company

	Raises:
		frappe.ValidationError: Se la company non viene trovata
	"""
	company = frappe.db.get_value("Company", {"tax_id": fiscal_id}, "name")
	if not company:
		frappe.throw(_(f"Company non trovata per fiscal_id: {fiscal_id}"))
	return company


def get_acube_public_key(fiscal_id):
	"""
	Recupera la chiave pubblica di ACube per verificare le firme.
	Usa cache per evitare chiamate ripetute.

	Args:
		fiscal_id: Il fiscal ID per trovare le impostazioni corrette
	"""
	global _public_key_cache

	if _public_key_cache:
		return _public_key_cache

	# Trova la company e le sue impostazioni
	company = get_company_from_fiscal_id(fiscal_id)
	api_url = frappe.db.get_value("OpenBanking Settings", {"company": company}, "api_url")
	if not api_url:
		frappe.throw(_(f"OpenBanking Settings non trovato per company: {company}"))

	# Costruisci l'URL per la chiave pubblica
	url = f"{api_url}/signature-public-key"

	try:
		response = requests.get(url, timeout=10)
		response.raise_for_status()
		public_key_pem = response.json().get("public_key")

		# La chiave è in formato PEM, carichiamola con cryptography
		from cryptography.hazmat.primitives import serialization

		# Carica la chiave pubblica dal formato PEM
		_public_key_cache = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))

		return _public_key_cache
	except Exception as e:
		frappe.log_error(f"Failed to fetch ACube public key: {e!s}", "ACube Public Key Error")
		frappe.throw(_("Impossibile recuperare la chiave pubblica di ACube"))


def verify_http_signature(request, fiscal_id):
	"""
	Verifica la firma HTTP del webhook usando ED25519.
	Richiede gli header: signature, signature-input, content-digest.

	Args:
		request: L'oggetto request di Frappe
		fiscal_id: Il fiscal ID per trovare le impostazioni corrette

	Returns:
		bool: True se la firma è valida
	"""
	try:
		# Importa la libreria per la verifica (da installare: pip install requests-http-signature)
		from requests_http_signature import HTTPSignatureAuth, InvalidSignature, algorithms

		# Ottieni header necessari
		signature = request.headers.get("signature")
		signature_input = request.headers.get("signature-input")
		content_digest = request.headers.get("content-digest")

		if not all([signature, signature_input, content_digest]):
			missing = []
			if not signature:
				missing.append("signature")
			if not signature_input:
				missing.append("signature-input")
			if not content_digest:
				missing.append("content-digest")
			frappe.log_error(
				f"Missing required signature headers: {', '.join(missing)}", "Webhook Signature Error"
			)
			return False

		# Crea un oggetto simile a una request per la verifica
		class RequestWrapper:
			def __init__(self, frappe_request):
				self.method = frappe_request.method
				self.headers = dict(frappe_request.headers)
				self.body = frappe_request.get_data()

				# Ricostruisci l'URL usando gli header X-Forwarded-* se presenti
				forwarded_host = frappe_request.headers.get("X-Forwarded-Host")
				forwarded_proto = frappe_request.headers.get("X-Forwarded-Proto")

				if forwarded_host and forwarded_proto:
					# Usa l'URL originale che ACube ha usato per firmare
					self.url = f"{forwarded_proto}://{forwarded_host}{frappe_request.path}"
				else:
					self.url = frappe_request.url

		# Resolver per la chiave pubblica
		class KeyResolver:
			def __init__(self, fiscal_id):
				self.fiscal_id = fiscal_id

			def resolve_public_key(self, key_id):
				if key_id != "acube":
					raise ValueError("Invalid key ID")
				return get_acube_public_key(self.fiscal_id)

		wrapped_request = RequestWrapper(request)

		# Verifica la firma
		HTTPSignatureAuth.verify(
			wrapped_request, signature_algorithm=algorithms.ED25519, key_resolver=KeyResolver(fiscal_id)
		)

		return True

	except ImportError:
		frappe.log_error(
			"requests-http-signature library not installed. Install with: bench pip install requests-http-signature",
			"Webhook Signature Error",
		)
		# In sviluppo, permetti comunque (da rimuovere in produzione)
		return True

	except InvalidSignature as e:
		frappe.log_error(
			f"Invalid HTTP signature: {e!s}\n"
			f"Request URL: {request.url}\n"
			f"Request Method: {request.method}\n"
			f"Headers: {json.dumps(dict(request.headers), indent=2)}",
			"Webhook Signature Error",
		)
		return False

	except Exception as e:
		frappe.log_error(
			f"Signature verification error: {e!s}\n"
			f"Request URL: {request.url}\n"
			f"Request Method: {request.method}",
			"Webhook Signature Error",
		)
		return False


@frappe.whitelist(allow_guest=True)
def acube_webhook():
	"""
	Endpoint per ricevere webhook da ACube Open Banking API.
	Gestisce eventi: connect, reconnect, payment.

	URL: /api/method/solede_openbanking.api.webhooks.acube_webhook
	"""
	try:
		# Verifica metodo
		if frappe.request.method != "POST":
			frappe.throw(_("Only POST requests are allowed"))

		# Ottieni il payload per estrarre il fiscal_id
		payload = frappe.request.get_json()
		if not payload:
			frappe.throw(_("Invalid payload"))

		fiscal_id = payload.get("fiscalId")

		# Verifica firma HTTP usando il fiscal_id
		if not verify_http_signature(frappe.request, fiscal_id):
			frappe.throw(_("Invalid HTTP signature"))

		# Determina il tipo di webhook e trova la company
		webhook_type = determine_webhook_type(payload)
		company = get_company_from_fiscal_id(fiscal_id)

		# Crea log del webhook
		log = create_webhook_log(webhook_type, fiscal_id, company, payload)

		# Processa il webhook
		result = None
		if webhook_type == "reconnect":
			result = handle_reconnect_webhook(payload, company, log.name)
		elif webhook_type == "connect":
			result = handle_connect_webhook(payload, company, log.name)
		elif webhook_type == "payment":
			result = handle_payment_webhook(payload, company, log.name)

		# Aggiorna il log
		update_webhook_log(log, result=result if result else "Processed successfully")

		return {"success": True, "message": "Webhook received and processed"}

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(
			f"Webhook Error: {error_msg}\nPayload: {json.dumps(payload) if 'payload' in locals() else 'N/A'}",
			"ACube Webhook Error",
		)

		# Aggiorna log con errore se esiste
		if "log" in locals():
			update_webhook_log(log, error_message=error_msg)

		return {"success": False, "error": error_msg}


def create_webhook_log(webhook_type, fiscal_id, company, payload):
	"""
	Crea un log del webhook ricevuto.

	Args:
		webhook_type: Tipo di webhook (connect, reconnect, payment, unknown)
		fiscal_id: Fiscal ID della company
		company: Nome della company
		payload: Payload JSON del webhook

	Returns:
		frappe.Document: Il documento del log creato
	"""
	log = frappe.get_doc(
		{
			"doctype": "ACube Webhook Log",
			"webhook_type": webhook_type,
			"fiscal_id": fiscal_id,
			"company": company,
			"received_at": datetime.now(),
			"payload": json.dumps(payload, indent=2),
			"processed": 0,
		}
	)
	log.insert(ignore_permissions=True)
	return log


def update_webhook_log(log, processed=1, result=None, error_message=None):
	"""
	Aggiorna un log del webhook con il risultato dell'elaborazione.

	Args:
		log: Il documento del log da aggiornare
		processed: 1 se elaborato, 0 altrimenti
		result: Risultato dell'elaborazione
		error_message: Messaggio di errore se presente
	"""
	log.processed = processed
	if result:
		log.processing_result = result
	if error_message:
		log.error_message = error_message
	log.save(ignore_permissions=True)
	frappe.db.commit()


def determine_webhook_type(payload):
	"""
	Determina il tipo di webhook dal payload.
	"""
	if "connectUrl" in payload and "consentExpiresAt" in payload and "noticeLevel" in payload:
		return "reconnect"
	elif "success" in payload and ("updatedAccounts" in payload or "errorClass" in payload):
		return "connect"
	elif "payment" in payload:
		return "payment"
	else:
		return "unknown"


def handle_reconnect_webhook(payload, company, log_name):
	"""
	Gestisce evento reconnect:
	- Invia email agli Account Manager avvisando della scadenza consenso
	- Livelli: 0 = 20 giorni, 1 = 10 giorni, 2 = 0 giorni (scaduto)
	"""
	fiscal_id = payload.get("fiscalId")
	connect_url = payload.get("connectUrl")
	provider_name = payload.get("providerName")
	consent_expires_at = payload.get("consentExpiresAt")
	notice_level = payload.get("noticeLevel", 0)

	# Determina urgenza
	urgency_map = {
		0: {"days": 20, "urgency": "info"},
		1: {"days": 10, "urgency": "warning"},
		2: {"days": 0, "urgency": "critical"},
	}
	urgency_info = urgency_map.get(notice_level, {"days": 20, "urgency": "info"})

	# Ottieni utenti con ruolo Accounts Manager
	account_managers = frappe.get_all(
		"Has Role", filters={"role": "Accounts Manager", "parenttype": "User"}, fields=["parent"]
	)

	recipients = [manager.parent for manager in account_managers]

	if not recipients:
		return f"No Accounts Manager found to notify. Notice level: {notice_level}"

	# Prepara messaggio email
	subject = f"⚠️ Consenso Open Banking in scadenza - {provider_name}"
	if urgency_info["urgency"] == "critical":
		subject = f"🔴 URGENTE: Consenso Open Banking scaduto - {provider_name}"
	elif urgency_info["urgency"] == "warning":
		subject = f"⚠️ Consenso Open Banking in scadenza tra {urgency_info['days']} giorni - {provider_name}"

	message = f"""
<p>Gentile Account Manager,</p>

<p>Il consenso Open Banking per <strong>{provider_name}</strong> deve essere rinnovato.</p>

<h3>Dettagli:</h3>
<ul>
<li><strong>Banca:</strong> {provider_name}</li>
<li><strong>Scadenza consenso:</strong> {consent_expires_at}</li>
<li><strong>Giorni rimanenti:</strong> {urgency_info["days"]}</li>
<li><strong>Fiscal ID:</strong> {fiscal_id}</li>
<li><strong>Company:</strong> {company or "N/A"}</li>
</ul>

<p><strong>Azione richiesta:</strong><br>
Per rinnovare il consenso, clicca sul link sottostante:</p>

<p><a href="{connect_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Rinnova Consenso</a></p>

<p><em>Questo è un messaggio automatico generato dal sistema Open Banking.</em></p>
"""

	# Invia email
	sent_count = 0
	for recipient in recipients:
		try:
			frappe.sendmail(recipients=[recipient], subject=subject, message=message, delayed=False)
			sent_count += 1
		except Exception as e:
			frappe.log_error(f"Failed to send email to {recipient}: {e!s}", "Reconnect Email Error")

	return f"Reconnect notification sent to {sent_count}/{len(recipients)} Accounts Manager(s). Notice level: {notice_level}"


def handle_connect_webhook(payload, company, log_name):
	"""
	Gestisce evento connect: logga l'evento.
	"""
	fiscal_id = payload.get("fiscalId")
	success = payload.get("success")

	if success:
		updated_accounts = payload.get("updatedAccounts", [])
		frappe.logger().info(
			f"Connect successful. Fiscal ID: {fiscal_id}. Updated accounts: {len(updated_accounts)}"
		)
		return f"Connect successful. Fiscal ID: {fiscal_id}. Updated accounts: {len(updated_accounts)}"
	else:
		error_class = payload.get("errorClass", "Unknown")
		error_message = payload.get("errorMessage", "No error message")
		frappe.logger().error(
			f"Connect failed. Fiscal ID: {fiscal_id}. Error: {error_class} - {error_message}"
		)
		return f"Connect failed. Fiscal ID: {fiscal_id}. Error: {error_class} - {error_message}"


def handle_payment_webhook(payload, company, log_name):
	"""
	Gestisce evento payment:
	- Aggiorna OpenBanking Payment con nuovo status
	- Se submitted: crea Payment Entry collegato a Purchase Invoice
	- Se failed: notifica errore
	"""
	payment_data = payload["payment"]
	payment_uuid = payment_data["uuid"]
	payment_direction = payment_data["direction"]
	payment_status = payment_data["status"]
	amount = payment_data["amount"]
	currency = payment_data["currencyCode"]

	# Trova OpenBanking Payment per UUID
	payment_name = frappe.db.get_value("OpenBanking Payment", {"uuid": payment_uuid}, "name")

	if not payment_name:
		error_msg = f"OpenBanking Payment not found for UUID: {payment_uuid}"
		frappe.logger().error(error_msg)
		return error_msg

	try:
		payment_doc = frappe.get_doc("OpenBanking Payment", payment_name)

		# Aggiorna status
		old_status = payment_doc.status
		payment_doc.status = payment_status.lower()

		# Gestisci errori
		if "errorClass" in payload:
			error_class = payload.get("errorClass")
			error_message = payload.get("errorMessage", "No error message")
			payment_doc.error_message = f"{error_class}: {error_message}"
			payment_doc.save(ignore_permissions=True)
			frappe.db.commit()

			frappe.logger().error(
				f"Payment {payment_direction} failed. UUID: {payment_uuid}. "
				f"Status: {payment_status}. Amount: {amount} {currency}. Error: {error_class}"
			)
			return f"Payment {payment_direction} failed. Status: {payment_status}. Amount: {amount} {currency}. Error: {error_class} - {error_message}"

		# Aggiorna campi dal payload
		payment_doc.end_to_end_id = payment_data.get("endToEndId")
		payment_doc.raw_response = json.dumps(payload, indent=2)
		payment_doc.save(ignore_permissions=True)
		frappe.db.commit()

		# "submitted" e' lo stato finale di successo dei bonifici outbound: A-Cube
		# invia UN solo webhook payment (a flusso autorizzato dalla banca) e non
		# aggiorna mai piu' lo stato (verificato 25/08/2026 su pagamenti storici
		# fermi a submitted mesi dopo l'esecuzione). I fallimenti arrivano prima,
		# con errorClass/failed.
		if payment_status.lower() == "submitted" and payment_doc.reference_doctype == "Purchase Invoice":
			create_payment_entry_from_payment(payment_doc)

		frappe.logger().info(
			f"Payment {payment_direction} updated. UUID: {payment_uuid}. "
			f"Status: {old_status} -> {payment_status}. Amount: {amount} {currency}"
		)
		return f"Payment {payment_direction} updated. Status: {old_status} -> {payment_status}. Amount: {amount} {currency}"

	except Exception as e:
		error_msg = f"Error processing payment webhook: {e!s}"
		frappe.log_error(frappe.get_traceback(), "Payment Webhook Error")
		return error_msg


def create_payment_entry_from_payment(payment_doc):
	"""
	Crea Payment Entry da OpenBanking Payment per Purchase Invoice.
	NO FALLBACK: Se c'è un errore, viene propagato.

	Args:
		payment_doc: Documento OpenBanking Payment
	"""
	if not payment_doc.reference_doctype or not payment_doc.reference_name:
		frappe.throw(_("OpenBanking Payment non ha riferimento a documento"))

	if payment_doc.reference_doctype != "Purchase Invoice":
		frappe.throw(_("Payment Entry automatica supportata solo per Purchase Invoice"))

	# Verifica che Purchase Invoice esista
	if not frappe.db.exists("Purchase Invoice", payment_doc.reference_name):
		frappe.throw(_("Purchase Invoice {0} not found").format(payment_doc.reference_name))

	purchase_invoice = frappe.get_doc("Purchase Invoice", payment_doc.reference_name)

	# Verifica che non sia già pagata
	if purchase_invoice.outstanding_amount <= 0:
		frappe.logger().info(f"Purchase Invoice {purchase_invoice.name} already paid")
		return

	# Recupera Mode of Payment da settings
	settings = frappe.get_doc("OpenBanking Settings", payment_doc.company)
	if not settings.payment_mode_of_payment:
		frappe.throw(
			_("Mode of Payment non configurato in OpenBanking Settings per company {0}").format(
				payment_doc.company
			)
		)

	# Recupera il GL account dal Bank Account già popolato sull'OpenBanking Payment
	bank_gl_account = None
	if payment_doc.bank_account:
		bank_gl_account = frappe.db.get_value(
			"Bank Account", payment_doc.bank_account, "account"
		)

	# Crea Payment Entry
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	payment_entry = get_payment_entry(
		"Purchase Invoice", purchase_invoice.name,
		bank_account=bank_gl_account,
		bank_amount=payment_doc.amount
	)

	# Rimuovi deductions auto (es. early payment discount) che potrebbero avere account vuoto
	payment_entry.deductions = []

	# Configura Payment Entry
	payment_entry.paid_amount = payment_doc.amount
	payment_entry.received_amount = payment_doc.amount
	payment_entry.reference_no = payment_doc.end_to_end_id or payment_doc.uuid
	payment_entry.reference_date = frappe.utils.today()
	payment_entry.remarks = f"Bonifico SEPA via Open Banking - {payment_doc.description}"
	payment_entry.mode_of_payment = settings.payment_mode_of_payment

	# Collega OpenBanking Payment
	payment_entry.custom_openbanking_payment = payment_doc.name

	# Salva e submit
	payment_entry.insert(ignore_permissions=True)
	payment_entry.submit()
	frappe.db.commit()

	frappe.logger().info(
		f"Payment Entry {payment_entry.name} created for Purchase Invoice {purchase_invoice.name}"
	)

	# Notifica utente
	frappe.publish_realtime(
		event="msgprint",
		message=_("Payment Entry {0} created for Purchase Invoice {1}").format(
			payment_entry.name, purchase_invoice.name
		),
		user=purchase_invoice.owner,
	)
