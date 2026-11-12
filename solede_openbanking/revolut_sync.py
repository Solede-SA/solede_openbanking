# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt
"""Movimenti dal collegamento diretto a Revolut Business: giro orario, «Sync Now», recupero da una data. Una
commissione compresa nel movimento nuovo diventa subito una spesa bancaria, se il collegamento lo chiede."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import NoReturn

import frappe
from frappe.utils import flt, get_datetime, get_url, getdate, now_datetime
from frappe.utils.user import get_users_with_role

from solede_openbanking import spese_bancarie
from solede_openbanking.api.revolut import (
	CONNECTION_STATUS_CONNECTED,
	RevolutAPIClient,
	RevolutAuthRevokedError,
	build_revolut_consent_url,
	create_bank_transaction,
	in_sospeso,
	normalize_revolut_api_tx,
)

REAUTH_NOTIFY_COOLDOWN_HOURS = 24

# Giorni riletti a ogni sync oltre a `last_sync_at`: Revolut filtra su created_at e una carta può restare «pending» per
# giorni; al primo passaggio viene scartata e senza sovrapposizione non verrebbe più ripresa. Idempotente per
# transaction_id + bank_account.
SYNC_OVERLAP_DAYS = 14

# Dati Revolut riempiti sulla tx già importata (da CSV o da un altro canale) se mancano
BACKFILL_FIELDS = ("revolut_balance_after", "revolut_completed_at", "transaction_type")
# Ciò che l'esito del giro dice di un movimento in sospeso, con i nomi dei campi del movimento bancario
IN_SOSPESO = ("date", "description", "withdrawal", "deposit", "currency")
# Confrontati con Revolut ma mai corretti qui: la riga può essere già riconciliata
COMPARED_FIELDS = ("date", "deposit", "withdrawal", "included_fee")


def _mark_connection_needs_reauth(connection_name: str, error_msg: str) -> None:
	"""Segna la connessione «Needs Reauth», lo scrive nell'Error Log e avvisa i responsabili contabili (una volta al
	giorno al massimo)."""
	conn = frappe.get_doc("Revolut Connection", connection_name)
	conn.db_set("connection_status", "Needs Reauth", update_modified=False)
	conn.db_set("last_auth_error", error_msg, update_modified=False)
	frappe.log_error(
		message=f"Revolut refresh_token revocato per {connection_name}: {error_msg}",
		title="Revolut: serve una nuova autorizzazione",
	)

	notified_at = conn.reauth_notified_at
	if notified_at and (now_datetime() - get_datetime(notified_at)).total_seconds() / 3600 < REAUTH_NOTIFY_COOLDOWN_HOURS:
		return

	destinatari = get_users_with_role("Accounts Manager")
	if not destinatari:
		frappe.throw(f"Revolut {connection_name} va autorizzato di nuovo, ma nessun utente ha il ruolo Accounts Manager per riceverne l'avviso.")
	consent_url = build_revolut_consent_url(conn)
	form_url = f"{get_url()}/app/revolut-connection/{connection_name}"
	frappe.sendmail(
		recipients=destinatari,
		subject=f"[REVOLUT] Re-autorizzazione richiesta — {conn.bank}",
		message=f"""
			<p>Il refresh_token per la connessione Revolut <strong>{conn.bank}</strong>
			è stato rifiutato dalla banca (probabile revoca dal Portal o app cancellata).</p>
			<p>Errore: <code>{frappe.utils.escape_html(error_msg)}</code></p>
			<p>Il sync orario è in pausa per questa connessione. Per riattivarla:</p>
			<ol>
				<li><a href="{consent_url}">Click qui per ri-autorizzare in Revolut</a> (apre il consent screen)</li>
				<li>Approva i permessi ({conn.permessi})</li>
				<li>Verrai reindirizzato al record <a href="{form_url}">{connection_name}</a></li>
				<li>Il sync orario riprenderà al prossimo giro da
					<code>{conn.last_sync_at or conn.cutover_date}</code> — nessuna transazione persa</li>
			</ol>
		""",
		reference_doctype="Revolut Connection",
		reference_name=connection_name,
		now=True,
	)
	conn.db_set("reauth_notified_at", now_datetime(), update_modified=False)


def sync_revolut_transactions() -> None:
	"""Giro orario: ogni Revolut Connection attiva, collegata, che importa i movimenti."""
	connections = frappe.get_all(
		"Revolut Connection",
		filters={"is_active": 1, "connection_status": CONNECTION_STATUS_CONNECTED, "importa_movimenti": 1},
		pluck="name",
	)
	for connection_name in connections:
		try:  # un collegamento che non va, anche nel segnarlo da autorizzare di nuovo, non ferma gli altri
			try:
				_sync_one_connection(connection_name)
			except RevolutAuthRevokedError as e:
				_mark_connection_needs_reauth(connection_name, str(e))
		except Exception:
			frappe.log_error(title=f"Revolut: movimenti non importati da {connection_name}")


def _revocato(connection_name: str, errore: Exception) -> NoReturn:
	_mark_connection_needs_reauth(connection_name, str(errore))
	frappe.throw(
		f"Refresh token Revolut revocato: la connessione è stata marcata 'Needs Reauth'. "
		f"Apri il record e clicca 'Riconnetti'. Dettaglio: {errore}"
	)


@frappe.whitelist()
def sync_now(connection_name: str) -> dict:
	"""Il giro di una sola Revolut Connection, subito: «Sync Now» sul collegamento e «Aggiorna i movimenti» del
	Riepilogo contabile."""
	frappe.has_permission("Revolut Connection", "write", doc=connection_name, throw=True)
	try:
		return _sync_one_connection(connection_name)
	except RevolutAuthRevokedError as e:
		_revocato(connection_name, e)


def _sync_one_connection(connection_name: str) -> dict:
	"""Sync incrementale: pull da `last_sync_at` (o dalla data di partenza) e avanza il cursore."""
	conn = frappe.get_doc("Revolut Connection", connection_name)
	client = RevolutAPIClient(connection_name)

	partenza = datetime.combine(get_datetime(conn.cutover_date).date(), time.min, tzinfo=timezone.utc)
	# la rilettura all'indietro non scende mai sotto la data di partenza: prima i movimenti sono di un'altra fonte
	from_dt = max(get_datetime(conn.last_sync_at).replace(tzinfo=timezone.utc) - timedelta(days=SYNC_OVERLAP_DAYS), partenza) if conn.last_sync_at else partenza
	to_dt = now_datetime()

	result = _pull_transactions(client, from_dt, to_dt)

	conn.db_set("last_sync_at", to_dt, update_modified=False)
	frappe.db.commit()
	_registra_regole()
	return result


def _conti_revolut():
	"""I Bank Account collegati a un conto Revolut: dove entrano i movimenti, e di quali società."""
	return frappe.get_all(
		"Bank Account", filters={"revolut_account_id": ["is", "set"], "disabled": 0}, fields=["name", "company", "revolut_account_id"],
	)


def _registra_regole() -> None:
	"""Le regole dei movimenti bancari (spese bancarie, acconti ai fornitori) subito dopo il giro, per le società dei
	conti Revolut: un movimento appena entrato non aspetta il giro di un'altra fonte."""
	for company in {conto.company for conto in _conti_revolut()}:
		spese_bancarie.registra(company)


def _pull_transactions(client: RevolutAPIClient, from_dt, to_dt) -> dict:
	"""Scarica e inserisce le transazioni nel range, idempotente per `transaction_id` + Bank Account
	(un cambio tra conti propri ha una leg per conto, stesso id). NON tocca `last_sync_at`:
	la gestione del cursore è del chiamante."""
	connessione = client._connection
	if not connessione.importa_movimenti:
		frappe.throw(f"{client.connection_name} non importa i movimenti: serve solo ai pagamenti, i movimenti di quel conto arrivano da un'altra fonte.")
	# revolut_account_id → (Bank Account, company), una volta sola
	account_map = {ba.revolut_account_id: (ba.name, ba.company) for ba in _conti_revolut()}

	# I movimenti prima della data di partenza sono di un'altra fonte (per esempio ACube): mai reimportati, anche
	# quando il giro rilegge SYNC_OVERLAP_DAYS indietro.
	partenza = getdate(connessione.cutover_date)
	# La commissione compresa nel movimento si registra subito come spesa bancaria, se il collegamento lo chiede.
	conto_commissioni = connessione.conto_commissioni if connessione.registra_commissioni else None

	created = skipped = updated = unmapped = 0
	mismatches = []
	sospesi = []  # non completati da Revolut: non entrano, si riportano nell'esito
	for tx in client.iter_transactions(from_dt, to_dt):
		for voce in in_sospeso(tx):
			mapping = account_map.get(voce.get("_account_id") or "")
			if mapping:
				sospesi.append({"bank_account": mapping[0], **{campo: voce[campo] for campo in IN_SOSPESO}})
		for normalized in normalize_revolut_api_tx(tx):
			if getdate(normalized["date"]) < partenza:
				skipped += 1
				continue
			mapping = account_map.get(normalized.get("_account_id") or "")
			if not mapping:
				unmapped += 1
				continue
			bank_account, company = mapping

			existing = frappe.db.get_value(
				"Bank Transaction",
				{"transaction_id": normalized["transaction_id"], "bank_account": bank_account},
				["name", *BACKFILL_FIELDS, *COMPARED_FIELDS],
				as_dict=True,
			)
			if not existing:
				nuovo = create_bank_transaction(bank_account, company, normalized)
				if conto_commissioni and normalized.get("included_fee"):
					spese_bancarie.registra_commissione_compresa(frappe.get_doc("Bank Transaction", nuovo), conto_commissioni)
				created += 1
				continue

			differences = _differences(existing, normalized)
			if differences:
				mismatches.append({"bank_transaction": existing.name, "differences": differences})

			updates = _backfill_updates(existing, normalized)
			if updates:
				frappe.db.set_value("Bank Transaction", existing.name, updates, update_modified=False)
				updated += 1
			else:
				skipped += 1

	return {
		"created": created,
		"skipped": skipped,
		"updated": updated,
		"unmapped": unmapped,
		"mismatches": mismatches,
		"in_sospeso": sospesi,
	}


def _backfill_updates(existing, normalized: dict) -> dict:
	"""Campi di BACKFILL_FIELDS vuoti sulla tx già importata e presenti nella voce Revolut."""
	return {
		field: normalized[field]
		for field in BACKFILL_FIELDS
		if normalized.get(field) not in (None, "") and not existing.get(field)
	}


def _differences(existing, normalized: dict) -> dict:
	"""{campo: (ERPNext, Revolut)} per i campi di COMPARED_FIELDS che non coincidono."""
	differences = {}
	for field in COMPARED_FIELDS:
		ours, theirs = _comparable(field, existing.get(field)), _comparable(field, normalized[field])
		if ours != theirs:
			differences[field] = (ours, theirs)
	return differences


def _comparable(field: str, value):
	"""Data in ISO, importi a due decimali."""
	return str(getdate(value)) if field == "date" else flt(value, 2)


@frappe.whitelist()
def backfill_connection(connection_name: str, from_date: str) -> dict:
	"""Recupero manuale: ri-scarica lo storico Revolut da `from_date` a ora, senza toccare `last_sync_at` (il cursore
	del giro resta dov'è, niente buchi). Idempotente per `transaction_id`: inserisce solo le transazioni mancanti, per
	esempio dopo aver mappato un nuovo conto Revolut su un Bank Account."""
	frappe.has_permission("Revolut Connection", "write", doc=connection_name, throw=True)
	from_dt = get_datetime(from_date)
	if not from_dt:
		frappe.throw("Data di partenza non valida.")
	if from_dt > now_datetime():
		frappe.throw("La data di partenza non può essere nel futuro.")

	client = RevolutAPIClient(connection_name)
	try:
		result = _pull_transactions(client, from_dt, now_datetime())
	except RevolutAuthRevokedError as e:
		_revocato(connection_name, e)
	frappe.db.commit()
	return result
