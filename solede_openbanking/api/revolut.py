# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt
"""
Client OAuth + REST per Revolut Business API.

Riferimenti documentazione Revolut:
- https://developer.revolut.com/docs/business/business-api
- https://developer.revolut.com/docs/business/get-transactions
- https://developer.revolut.com/docs/guides/manage-accounts/get-started/make-your-first-api-request
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import secrets
import urllib.parse as _urlparse
from typing import Iterator

import frappe
import jwt
import requests
from frappe import _
from frappe.utils import get_datetime

from solede_openbanking.solede_openbanking.doctype.csv_bank_import.csv_bank_import import (
	insert_bank_transaction,
)
from solede_openbanking.solede_openbanking.parsers.base import movement
from solede_openbanking.solede_openbanking.parsers.revolut_business import (
	build_revolut_description,
)

# Stati della Revolut Connection
CONNECTION_STATUS_NEVER = "Never Connected"
CONNECTION_STATUS_CONNECTED = "Connected"
CONNECTION_STATUS_NEEDS_REAUTH = "Needs Reauth"

REQUEST_TIMEOUT = 30
TX_PAGE_SIZE = 1000


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _endpoints(environment: str) -> dict[str, str]:
	if environment == "Sandbox":
		return {
			"authorize": "https://sandbox-business.revolut.com/app-confirm",
			"token": "https://sandbox-b2b.revolut.com/api/1.0/auth/token",
			"api": "https://sandbox-b2b.revolut.com/api/1.0",
		}
	return {
		"authorize": "https://business.revolut.com/app-confirm",
		"token": "https://b2b.revolut.com/api/1.0/auth/token",
		"api": "https://b2b.revolut.com/api/1.0",
	}


# ---------------------------------------------------------------------------
# Eccezioni dedicate
# ---------------------------------------------------------------------------

class RevolutAuthRevokedError(Exception):
	"""Sollevato quando Revolut rifiuta il refresh_token (revoca / scadenza / app cancellata)."""


class RevolutAPIError(Exception):
	"""Errore generico HTTP dalla Business API."""


# ---------------------------------------------------------------------------
# JWT client_assertion (RS256)
# ---------------------------------------------------------------------------

def _build_jwt_assertion(client_id: str, private_key_pem: str, redirect_uri: str) -> str:
	"""Costruisce il JWT firmato RS256 da usare come `client_assertion` su Revolut.

	Spec Revolut:
	- iss = host del redirect_uri (senza schema)
	- sub = client_id
	- aud = "https://revolut.com"
	- exp <= 1 ora
	"""
	host = _urlparse.urlparse(redirect_uri).hostname or ""
	if not host:
		frappe.throw(_("Redirect URI senza host valido: {0}").format(redirect_uri))

	now = int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp())
	payload = {
		"iss": host,
		"sub": client_id,
		"aud": "https://revolut.com",
		"iat": now,
		"exp": now + 30 * 60,  # 30 minuti
	}
	return jwt.encode(payload, private_key_pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# State HMAC (CSRF protection sull'OAuth callback)
# ---------------------------------------------------------------------------

_STATE_NONCE_BYTES = 16


def _state_secret() -> bytes:
	secret = frappe.local.conf.get("secret_key") or frappe.local.conf.get("encryption_key")
	if not secret:
		frappe.throw(_("Site config senza secret_key/encryption_key — impossibile firmare lo state OAuth."))
	return secret.encode("utf-8")


def build_state_hmac(connection_name: str) -> str:
	nonce = secrets.token_hex(_STATE_NONCE_BYTES)
	mac = hmac.new(_state_secret(), f"{connection_name}|{nonce}".encode("utf-8"), hashlib.sha256).hexdigest()
	return f"{connection_name}|{nonce}|{mac}"


def verify_state_hmac(state: str) -> str:
	"""Restituisce il connection_name se la firma è valida, altrimenti solleva."""
	parts = (state or "").split("|")
	if len(parts) != 3:
		frappe.throw(_("State OAuth malformato."))
	connection_name, nonce, mac = parts
	expected = hmac.new(
		_state_secret(),
		f"{connection_name}|{nonce}".encode("utf-8"),
		hashlib.sha256,
	).hexdigest()
	if not hmac.compare_digest(expected, mac):
		frappe.throw(_("State OAuth non verificato (HMAC mismatch)."))
	return connection_name


# ---------------------------------------------------------------------------
# Consent URL
# ---------------------------------------------------------------------------

def build_revolut_consent_url(connection) -> str:
	endpoints = _endpoints(connection.environment)
	state = build_state_hmac(connection.name)
	query = _urlparse.urlencode(
		{
			"client_id": connection.client_id,
			"redirect_uri": connection.redirect_uri,
			"response_type": "code",
			"scope": connection.permessi,
			"state": state,
		}
	)
	return f"{endpoints['authorize']}?{query}"


# ---------------------------------------------------------------------------
# RevolutAPIClient
# ---------------------------------------------------------------------------

class RevolutAPIClient:
	"""Client incapsula auth + fetch transazioni per una specifica Revolut Connection.

	Ogni istanza:
	- carica credenziali (cifrate) dal record Revolut Connection
	- ottiene un access_token al primo bisogno (refresh dal refresh_token)
	- espone iter_transactions() come generatore paginato
	"""

	def __init__(self, connection_name: str):
		self.connection_name = connection_name
		self._connection = frappe.get_doc("Revolut Connection", connection_name)
		if not self._connection.is_active:
			frappe.throw(_("Revolut Connection {0} non è attiva.").format(connection_name))
		self._endpoints = _endpoints(self._connection.environment)
		self._access_token: str | None = None

	# --- credenziali ----------------------------------------------------

	def _private_key(self) -> str:
		pk = self._connection.get_password("private_key", raise_exception=True)
		if not pk:
			frappe.throw(_("Private Key mancante per {0}.").format(self.connection_name))
		return pk

	def _refresh_token(self) -> str:
		rt = self._connection.get_password("refresh_token", raise_exception=False)
		if not rt:
			raise RevolutAuthRevokedError(
				f"Refresh token assente per {self.connection_name}: bootstrap OAuth richiesto."
			)
		return rt

	# --- token exchange -------------------------------------------------

	def _post_token(self, data: dict) -> dict:
		assertion = _build_jwt_assertion(
			client_id=self._connection.client_id,
			private_key_pem=self._private_key(),
			redirect_uri=self._connection.redirect_uri,
		)
		body = {
			**data,
			"client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
			"client_assertion": assertion,
		}
		response = requests.post(
			self._endpoints["token"],
			data=body,
			headers={"Content-Type": "application/x-www-form-urlencoded"},
			timeout=REQUEST_TIMEOUT,
		)
		# Revoca / token rifiutato
		if response.status_code in (400, 401):
			try:
				err = response.json()
			except ValueError:
				err = {}
			if err.get("error") in ("invalid_grant", "invalid_client", "unauthorized_client"):
				raise RevolutAuthRevokedError(
					err.get("error_description") or err.get("error") or response.text
				)
		response.raise_for_status()
		return response.json()

	def exchange_code(self, code: str) -> dict:
		"""Bootstrap iniziale: scambia un authorization_code per access+refresh token."""
		return self._post_token({"grant_type": "authorization_code", "code": code})

	def refresh_access_token(self) -> str:
		tokens = self._post_token({"grant_type": "refresh_token", "refresh_token": self._refresh_token()})
		self._access_token = tokens["access_token"]
		return self._access_token

	# --- API calls ------------------------------------------------------

	def _ensure_access_token(self) -> str:
		if not self._access_token:
			self.refresh_access_token()
		return self._access_token  # type: ignore[return-value]

	def get_accounts(self) -> list[dict]:
		"""Lista degli account Revolut Business (GET /accounts)."""
		response = self._api_get("/accounts")
		return response if isinstance(response, list) else []

	def get_transactions_page(self, params: dict) -> list[dict]:
		"""Singola pagina di GET /transactions. Solitamente usata via iter_transactions()."""
		response = self._api_get("/transactions", params=params)
		return response if isinstance(response, list) else []

	def _api(self, method: str, path: str, **kwargs) -> list | dict | None:
		"""Una chiamata all'interfaccia di Revolut; `kwargs` vanno a requests (params, json). Senza contenuto (204)
		restituisce None."""
		url = f"{self._endpoints['api']}{path}"

		def chiama():
			headers = {"Authorization": f"Bearer {self._ensure_access_token()}", "Accept": "application/json"}
			return requests.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)

		response = chiama()
		# Token scaduto durante la chiamata: refresh + retry una sola volta
		if response.status_code == 401:
			self.refresh_access_token()
			response = chiama()
		if response.status_code >= 400:
			raise RevolutAPIError(f"{method} {path} → HTTP {response.status_code}: {response.text}")
		return response.json() if response.content else None

	def _api_get(self, path: str, params: dict | None = None) -> list | dict:
		return self._api("GET", path, params=params or {})

	# --- pagamenti (permessi READ,WRITE: controparti e bozze, che partono solo dall'app Revolut) ---------------
	# Gli IBAN arrivano già puliti (iban_pulito): li puliscono pagamenti_della_societa e l'anagrafica del fornitore.

	def conto_da_iban(self, iban: str) -> str:
		"""L'id del conto Revolut in euro con quell'IBAN."""
		for conto in self.get_accounts():
			if conto.get("currency") == "EUR" and any(
				iban_pulito(d.get("iban")) == iban for d in self._api_get(f"/accounts/{conto['id']}/bank-details")
			):
				return conto["id"]
		frappe.throw(_("Nessun conto Revolut in euro di {0} ha l'IBAN {1}.").format(self.connection_name, iban))

	def verifica_nome(self, iban: str, nome: str) -> dict:
		"""Verifica europea del beneficiario: il nome corrisponde all'IBAN? `result_code` matched, close_match,
		not_matched, cannot_be_checked, temporarily_unavailable; con close_match anche il nome vero in `company_name`."""
		return self._api(
			"POST", "/account-name-validation",
			json={"iban": iban, "recipient_country": iban[:2], "recipient_currency": "EUR", "company_name": nome},
		)

	def controparte(self, iban: str, nome: str) -> tuple[str, str]:
		"""(id della controparte, id del suo conto) per quell'IBAN; se Revolut non la conosce ancora la aggiunge."""
		for controparte in self._api_get("/counterparties", params={"iban": iban}):
			for conto in controparte.get("accounts") or []:
				if iban_pulito(conto.get("iban")) == iban:
					return controparte["id"], conto["id"]
		nuova = self._api("POST", "/counterparty", json={"company_name": nome, "bank_country": iban[:2], "currency": "EUR", "iban": iban})
		return nuova["id"], nuova["accounts"][0]["id"]

	def crea_bozza(self, titolo: str, conto: str, controparte: tuple[str, str], importo: float, riferimento: str) -> str:
		"""Una bozza di bonifico in euro: diventa pagamento solo quando la si invia dall'app Revolut."""
		pagamento = {
			"account_id": conto,
			"receiver": {"counterparty_id": controparte[0], "account_id": controparte[1]},
			"amount": importo,
			"currency": "EUR",
			"reference": riferimento,
		}
		return self._api("POST", "/payment-drafts", json={"title": titolo, "payments": [pagamento]})["id"]

	def elimina_bozza(self, bozza: str) -> None:
		self._api("DELETE", f"/payment-drafts/{bozza}")

	def bozze(self) -> list[dict]:
		"""Le bozze create dall'interfaccia e non ancora inviate dall'app (id, title, scheduled_for)."""
		return self._api_get("/payment-drafts")["payment_orders"]

	def iter_transactions(
		self,
		from_dt: _dt.datetime,
		to_dt: _dt.datetime,
	) -> Iterator[dict]:
		"""Yield transazioni Revolut completate nell'intervallo, ordine cronologico inverso.

		Paginazione: Revolut restituisce max 1000 risultati ordinati per `created_at` DESC.
		Per la pagina successiva si richiama con `to = created_at dell'ultimo elemento`.
		Continuiamo finché abbiamo `created_at >= from_dt`.
		"""
		current_to = to_dt
		from_iso = _to_iso8601(from_dt)
		while True:
			page = self.get_transactions_page(
				{
					"from": from_iso,
					"to": _to_iso8601(current_to),
					"count": TX_PAGE_SIZE,
				}
			)
			if not page:
				return
			for tx in page:
				yield tx
			if len(page) < TX_PAGE_SIZE:
				return
			# pagina successiva: usa il created_at del più vecchio elemento (ultimo dell'array DESC)
			oldest_created_at = page[-1].get("created_at")
			if not oldest_created_at:
				return
			next_to = get_datetime(oldest_created_at)
			if next_to <= from_dt:
				return
			current_to = next_to


def iban_pulito(valore: str | None) -> str:
	return (valore or "").replace(" ", "").upper()


def _to_iso8601(value: _dt.datetime) -> str:
	if value.tzinfo is None:
		value = value.replace(tzinfo=_dt.timezone.utc)
	return value.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# Normalizzazione transazioni: JSON Revolut → schema BankCSVParser
# ---------------------------------------------------------------------------

def normalize_revolut_api_tx(tx: dict) -> list[dict]:
	"""Trasforma una transazione Revolut in voci allineate a `BankCSVParser.parse()`, una per leg.

	Lista vuota se la transazione non va importata: stato diverso da completed (una
	carta resta «pending» anche per giorni: la riprende un sync successivo grazie a
	SYNC_OVERLAP_DAYS) oppure nessuna leg. Le leg a importo e commissione zero sono
	verifiche carta: nessun movimento, Revolut non le stampa negli estratti.
	Un cambio tra conti propri ha due leg, una per conto.
	"""
	if (tx.get("state") or "").lower() != "completed":
		return []
	return [_normalize_leg(tx, leg) for leg in tx.get("legs") or [] if leg.get("amount") or leg.get("fee")]


def _normalize_leg(tx: dict, leg: dict) -> dict:
	amount = float(leg.get("amount") or 0.0)
	fee = float(leg.get("fee") or 0.0)
	currency = leg.get("currency") or ""

	# bill_amount/bill_currency: campi multi-currency (card payment in valuta diversa)
	bill_currency = (leg.get("bill_currency") or "").strip()
	bill_amount = float(leg.get("bill_amount") or 0.0)

	orig_currency = bill_currency if bill_currency and bill_currency != currency else None
	orig_amount = abs(bill_amount) if orig_currency else 0.0

	# IBAN beneficiario: cercato nel counterparty (per transfer in uscita)
	counterparty = leg.get("counterparty") or {}
	beneficiary_iban = (counterparty.get("iban") or counterparty.get("account_no") or "").strip() or None

	# Al secondo, per ordinare le tx dello stesso giorno (Frappe Datetime senza fuso né microsecondi)
	completed_at = get_datetime(tx.get("completed_at") or tx.get("updated_at") or tx.get("created_at"))

	merchant = tx.get("merchant") or {}
	payer_name = (
		(counterparty.get("name") if counterparty else None)
		or merchant.get("name")
		or None
	)

	balance_after = leg.get("balance")

	return {
		"date": completed_at.date().isoformat(),
		"transaction_id": tx.get("id"),
		"description": _build_description(tx, leg),
		# La commissione esce insieme all'importo: movimento totale, commissione a parte
		**movement(amount - fee, fee),
		"currency": currency,
		"transaction_type": (tx.get("type") or "").strip(),
		"payer": payer_name,
		"solede_orig_currency": orig_currency,
		"solede_orig_amount": orig_amount,
		"solede_beneficiary_iban": beneficiary_iban,
		"revolut_balance_after": float(balance_after) if balance_after is not None else None,
		"revolut_completed_at": completed_at.strftime("%Y-%m-%d %H:%M:%S"),
		"_account_id": leg.get("account_id"),  # per resolve Bank Account
	}


def _build_description(tx: dict, leg: dict) -> str:
	desc = build_revolut_description(
		description=leg.get("description") or "",
		reference=tx.get("reference") or "",
		tx_type=tx.get("type") or "",
	)
	return desc or (tx.get("id") or "")


# ---------------------------------------------------------------------------
# Endpoint OAuth (whitelisted)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def start_oauth_flow(connection: str) -> dict:
	"""Restituisce l'URL del consent screen Revolut per il record indicato.

	Chiamato dal bottone "Connetti a Revolut" lato JS.
	"""
	frappe.has_permission("Revolut Connection", "write", doc=connection, throw=True)
	conn = frappe.get_doc("Revolut Connection", connection)
	if not conn.is_active:
		frappe.throw(_("Revolut Connection {0} non è attiva.").format(connection))
	return {"consent_url": build_revolut_consent_url(conn)}


@frappe.whitelist()
def list_accounts(connection: str) -> list[dict]:
	"""Lista gli account Revolut disponibili (GET /accounts) e indica
	quali sono già mappati a un Bank Account ERPNext."""
	frappe.has_permission("Revolut Connection", "read", doc=connection, throw=True)
	client = RevolutAPIClient(connection)
	client.refresh_access_token()
	accounts = client.get_accounts()

	# Map Revolut UUID → Bank Account name (ERPNext) per indicare lo stato
	uuids = [a.get("id") for a in accounts if a.get("id")]
	mapped = {}
	if uuids:
		rows = frappe.get_all(
			"Bank Account",
			filters={"revolut_account_id": ["in", uuids]},
			fields=["name", "revolut_account_id", "company"],
		)
		for r in rows:
			mapped[r["revolut_account_id"]] = {"bank_account": r["name"], "company": r["company"]}

	enriched = []
	for a in accounts:
		uuid = a.get("id")
		balance_minor = a.get("balance") or 0
		# Revolut: balance numerico in unità "minor" (es. centesimi)? In realtà nei docs è già in unità
		# major. Manteniamo il valore come-is e lasciamo il display al client.
		enriched.append(
			{
				"uuid": uuid,
				"name": a.get("name") or _("(senza nome)"),
				"currency": a.get("currency"),
				"balance": balance_minor,
				"state": a.get("state"),
				"public": bool(a.get("public")),
				"created_at": a.get("created_at"),
				"mapped_to": mapped.get(uuid),
			}
		)
	return enriched


@frappe.whitelist()
def unmap_account(bank_account: str) -> str:
	"""Rimuove `revolut_account_id` dal Bank Account indicato."""
	frappe.has_permission("Bank Account", "write", doc=bank_account, throw=True)
	if not frappe.db.exists("Bank Account", bank_account):
		frappe.throw(_("Bank Account {0} non trovato.").format(bank_account))
	frappe.db.set_value("Bank Account", bank_account, "revolut_account_id", None)
	frappe.db.commit()
	return bank_account


@frappe.whitelist()
def map_account_to_bank_account(connection: str, revolut_account_uuid: str, bank_account: str) -> str:
	"""Setta `revolut_account_id` sul Bank Account indicato. Idempotente."""
	frappe.has_permission("Revolut Connection", "read", doc=connection, throw=True)
	frappe.has_permission("Bank Account", "write", doc=bank_account, throw=True)
	if not frappe.db.exists("Revolut Connection", connection):
		frappe.throw(_("Revolut Connection {0} non trovata.").format(connection))
	if not frappe.db.exists("Bank Account", bank_account):
		frappe.throw(_("Bank Account {0} non trovato.").format(bank_account))

	# Sblocco eventuale assegnazione precedente dello stesso UUID a un altro Bank Account
	other = frappe.get_all(
		"Bank Account",
		filters={"revolut_account_id": revolut_account_uuid, "name": ["!=", bank_account]},
		pluck="name",
	)
	if other:
		frappe.throw(
			_("Il Revolut Account UUID {0} è già mappato al Bank Account {1}. "
			  "Rimuovi la mappatura prima di riassegnarla.").format(revolut_account_uuid, other[0])
		)

	frappe.db.set_value("Bank Account", bank_account, "revolut_account_id", revolut_account_uuid)
	frappe.db.commit()
	return bank_account


@frappe.whitelist()
def callback(code: str | None = None, state: str | None = None, **kwargs) -> None:
	"""Endpoint di redirect chiamato da Revolut dopo il consent.

	- Verifica HMAC dello state (se Revolut lo restituisce; sandbox spesso non lo fa)
	- Scambia code per access+refresh token
	- Sovrascrive il refresh_token (cifrato) e ripristina lo stato Connected
	- Redirige al form Revolut Connection
	"""
	if not code:
		frappe.throw(_("Callback senza code."))

	if state:
		connection_name = verify_state_hmac(state)
	else:
		# Revolut Business (almeno in sandbox) non rispedisce lo state nel redirect.
		# Fallback: identifichiamo l'unica Revolut Connection in attesa di consent.
		connection_name = _resolve_pending_connection()

	conn = frappe.get_doc("Revolut Connection", connection_name)

	client = RevolutAPIClient(connection_name)
	tokens = client.exchange_code(code)

	conn.refresh_token = tokens["refresh_token"]
	conn.connection_status = CONNECTION_STATUS_CONNECTED
	conn.last_auth_error = None
	conn.reauth_notified_at = None
	conn.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = f"/app/revolut-connection/{connection_name}"


def saldo(bank_account: str) -> float:
	"""Il saldo vero del conto Revolut mappato sul Bank Account, in sola lettura (il collegamento ha il nome della banca)."""
	conto, banca = frappe.db.get_value("Bank Account", bank_account, ["revolut_account_id", "bank"])
	for c in RevolutAPIClient(banca).get_accounts():
		if c["id"] == conto:
			return float(c["balance"])
	frappe.throw(_("Il conto Revolut {0} di {1} non c'è fra quelli del collegamento {2}.").format(conto, bank_account, banca))


COLLEGAMENTI_PER_PAGARE = {"is_active": 1, "permessi": "READ,WRITE"}


def pagamenti_della_societa(company: str):
	"""Il conto Revolut da cui la società può preparare bonifici: un collegamento attivo con i permessi di scrittura e
	il conto della società in quella banca (il collegamento ha il nome della banca). None se la società non ce l'ha."""
	banche = frappe.get_all("Revolut Connection", filters=COLLEGAMENTI_PER_PAGARE, pluck="bank")
	conti = banche and frappe.get_all(
		"Bank Account",
		filters={"company": company, "is_company_account": 1, "disabled": 0, "bank": ["in", banche], "iban": ["is", "set"]},
		fields=["name", "bank", "iban"],
	)
	if not conti:
		return None
	if len(conti) > 1:
		frappe.throw(_("{0} ha più conti Revolut collegati: {1}. Ne serve uno solo per i bonifici.").format(company, ", ".join(c.name for c in conti)))
	return frappe._dict(collegamento=conti[0].bank, bank_account=conti[0].name, iban=iban_pulito(conti[0].iban))


def _resolve_pending_connection() -> str:
	"""Cerca l'unica Revolut Connection attiva in attesa di consent (status != Connected).

	Usato come fallback quando Revolut non restituisce lo `state` nel redirect.
	"""
	pending = frappe.get_all(
		"Revolut Connection",
		filters={
			"is_active": 1,
			"connection_status": ["in", [CONNECTION_STATUS_NEVER, CONNECTION_STATUS_NEEDS_REAUTH]],
		},
		fields=["name"],
		order_by="modified desc",
		limit_page_length=2,
	)
	if not pending:
		frappe.throw(
			_("Nessuna Revolut Connection in attesa di consent. Apri il record e clicca 'Connetti a Revolut'.")
		)
	if len(pending) > 1:
		names = ", ".join(p["name"] for p in pending)
		frappe.throw(
			_(
				"Più di una Revolut Connection in attesa di consent: {0}. "
				"Imposta a 'Disabled' quelle non interessate prima di procedere."
			).format(names)
		)
	return pending[0]["name"]


# ---------------------------------------------------------------------------
# Bank Transaction creation (riuso semantica di csv_bank_import)
# ---------------------------------------------------------------------------

def resolve_bank_account_from_revolut_account_id(revolut_account_id: str) -> str | None:
	if not revolut_account_id:
		return None
	return frappe.db.get_value(
		"Bank Account", {"revolut_account_id": revolut_account_id, "disabled": 0}, "name"
	)


def create_bank_transaction(bank_account: str, company: str, normalized: dict) -> str:
	"""Crea (e submit) una Bank Transaction. Wrapper su `insert_bank_transaction`
	con `ignore_permissions=True` (chiamata dal cron, non da utente)."""
	return insert_bank_transaction(bank_account, company, normalized, ignore_permissions=True)
