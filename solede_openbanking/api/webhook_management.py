# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from solede_openbanking.api.client import ACubeAPIClient


@frappe.whitelist()
def configure_all_webhooks(company):
	"""
	Configura tutti i webhook (connect, reconnect, payment) su ACube.
	Crea un webhook separato per ogni tipo di evento.
	Se un webhook fallisce, tutti i webhook vengono rimossi (rollback completo).

	Args:
		company: Nome della company

	Returns:
		dict: {"success": True, "message": "...", "configured_webhooks": [...]}
	"""
	settings = frappe.get_doc("OpenBanking Settings", company)
	client = ACubeAPIClient(company)

	if not settings.webhook_base_url:
		frappe.throw(_("Webhook Base URL non configurato"))

	if not settings.webhooks:
		frappe.throw(_("Nessun webhook configurato nella tabella"))

	configured_webhooks = []

	try:
		# Per ogni webhook nella child table
		for webhook_row in settings.webhooks:
			# Salta se già configurato
			if webhook_row.webhook_uuid and webhook_row.configured:
				frappe.logger().info(
					f"Webhook {webhook_row.event} già configurato con UUID {webhook_row.webhook_uuid}, salto"
				)
				continue

			event = webhook_row.event
			target_url = webhook_row.target_url or settings.webhook_base_url

			# Prepara payload per creare webhook
			payload = {"event": event, "targetUrl": target_url}

			# Aggiungi autenticazione opzionale
			if webhook_row.authentication_type:
				payload["authentication"] = {
					"type": webhook_row.authentication_type,
					"key": webhook_row.authentication_key,
					"token": webhook_row.authentication_token,
				}

			# Crea webhook su ACube
			response_data = client.post(
				"webhooks", f"Create Webhook {event}", payload=payload, expected_status_codes=[201]
			)

			webhook_uuid = response_data.get("uuid")
			if not webhook_uuid:
				frappe.throw(_("UUID webhook non ricevuto per evento {0}").format(event))

			# Salva UUID nella child table
			frappe.db.set_value(
				"OpenBanking Webhook", webhook_row.name, {"webhook_uuid": webhook_uuid, "configured": 1}
			)

			configured_webhooks.append({"event": event, "uuid": webhook_uuid})

			frappe.logger().info(f"Webhook {event} configured with UUID {webhook_uuid}")

	except Exception as e:
		error_message = str(e)
		frappe.log_error(f"Error configuring webhooks: {error_message}", "Configure Webhooks Error")

		# Rollback: rimuovi tutti i webhook creati
		for webhook_info in configured_webhooks:
			try:
				client.delete(
					f"webhooks/{webhook_info['uuid']}",
					f"Delete Webhook {webhook_info['event']} (rollback)",
					expected_status_codes=[204],
				)
				frappe.logger().info(
					f"Rolled back webhook {webhook_info['event']} (UUID: {webhook_info['uuid']})"
				)
			except Exception as rollback_error:
				frappe.log_error(
					f"Failed to rollback webhook {webhook_info['uuid']}: {rollback_error!s}",
					"Webhook Rollback Error",
				)

		# Reset child table
		for webhook_row in settings.webhooks:
			frappe.db.set_value(
				"OpenBanking Webhook", webhook_row.name, {"webhook_uuid": None, "configured": 0}
			)

		frappe.db.commit()
		frappe.throw(
			_(
				"Errore durante la configurazione dei webhook: {0}. Tutti i webhook sono stati rimossi."
			).format(error_message)
		)

	frappe.db.commit()

	# Calcola quanti erano già configurati
	total_webhooks = len(settings.webhooks)
	already_configured = total_webhooks - len(configured_webhooks)

	if len(configured_webhooks) == 0:
		message = _("Tutti i webhook ({0}) sono già configurati").format(total_webhooks)
	elif already_configured == 0:
		message = _("Configurati {0} webhook con successo").format(len(configured_webhooks))
	else:
		message = _("Configurati {0} nuovi webhook. {1} erano già configurati").format(
			len(configured_webhooks), already_configured
		)

	return {"success": True, "message": message, "configured_webhooks": configured_webhooks}


@frappe.whitelist()
def sync_webhooks(company):
	"""
	Sincronizza i webhook locali con quelli configurati su ACube.
	Recupera la lista dei webhook da ACube e aggiorna lo stato nella child table.

	Args:
		company: Nome della company

	Returns:
		dict: {"success": True, "webhooks": [...]}
	"""
	settings = frappe.get_doc("OpenBanking Settings", company)
	client = ACubeAPIClient(company)

	try:
		# Ottieni lista webhook da ACube
		webhooks_data = client.get("webhooks", "Get Webhooks")

		# Crea mappa UUID -> webhook da ACube
		acube_webhooks = {wh.get("uuid"): wh for wh in webhooks_data}

		# Aggiorna child table
		for webhook_row in settings.webhooks:
			if webhook_row.webhook_uuid and webhook_row.webhook_uuid in acube_webhooks:
				# Webhook esiste su ACube - marca come configurato
				frappe.db.set_value("OpenBanking Webhook", webhook_row.name, "configured", 1)
			else:
				# Webhook non esiste su ACube - marca come non configurato
				frappe.db.set_value(
					"OpenBanking Webhook", webhook_row.name, {"webhook_uuid": None, "configured": 0}
				)

		frappe.db.commit()

		return {
			"success": True,
			"message": _("Sincronizzati {0} webhook").format(len(webhooks_data)),
			"webhooks": webhooks_data,
		}

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Error syncing webhooks: {error_msg}", "Sync Webhooks Error")
		frappe.throw(_("Errore durante la sincronizzazione dei webhook: {0}").format(error_msg))


@frappe.whitelist()
def remove_all_webhooks(company):
	"""
	Rimuove tutti i webhook configurati su ACube.
	Aggiorna la child table resettando UUID e status.

	Args:
		company: Nome della company

	Returns:
		dict: {"success": True, "message": "...", "removed_count": count}
	"""
	settings = frappe.get_doc("OpenBanking Settings", company)
	client = ACubeAPIClient(company)

	removed_count = 0

	try:
		# Per ogni webhook nella child table
		for webhook_row in settings.webhooks:
			if webhook_row.webhook_uuid and webhook_row.configured:
				try:
					# Elimina webhook su ACube
					client.delete(
						f"webhooks/{webhook_row.webhook_uuid}",
						f"Delete Webhook {webhook_row.event}",
						expected_status_codes=[204],
					)

					# Reset child table row
					frappe.db.set_value(
						"OpenBanking Webhook", webhook_row.name, {"webhook_uuid": None, "configured": 0}
					)

					removed_count += 1
					frappe.logger().info(
						f"Removed webhook {webhook_row.event} (UUID: {webhook_row.webhook_uuid})"
					)

				except Exception as e:
					# Continua con gli altri anche se uno fallisce
					frappe.log_error(
						f"Failed to remove webhook {webhook_row.webhook_uuid}: {e!s}", "Remove Webhook Error"
					)

		frappe.db.commit()

		return {
			"success": True,
			"message": _("Rimossi {0} webhook").format(removed_count),
			"removed_count": removed_count,
		}

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Error removing webhooks: {error_msg}", "Remove Webhooks Error")
		frappe.throw(_("Errore durante la rimozione dei webhook: {0}").format(error_msg))


@frappe.whitelist()
def test_webhook(company, event):
	"""
	Testa un webhook specifico recuperando le sue informazioni da ACube.

	Args:
		company: Nome della company
		event: Tipo di evento (connect, reconnect, payment)

	Returns:
		dict: {"success": True, "message": "...", "test_result": {...}}
	"""
	settings = frappe.get_doc("OpenBanking Settings", company)
	client = ACubeAPIClient(company)

	# Trova il webhook nella child table
	webhook_row = None
	for wh in settings.webhooks:
		if wh.event == event:
			webhook_row = wh
			break

	if not webhook_row:
		frappe.throw(_("Webhook per evento {0} non trovato").format(event))

	if not webhook_row.webhook_uuid or not webhook_row.configured:
		frappe.throw(_("Webhook per evento {0} non configurato").format(event))

	try:
		# Recupera informazioni webhook da ACube
		response_data = client.get(f"webhooks/{webhook_row.webhook_uuid}", f"Test Webhook {event}")

		return {
			"success": True,
			"message": _("Test webhook {0} completato").format(event),
			"test_result": response_data,
		}

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Error testing webhook {event}: {error_msg}", "Test Webhook Error")
		frappe.throw(_("Errore durante il test del webhook: {0}").format(error_msg))
