# Copyright (c) 2024-2025, Solede SA and contributors
# For license information, please see license.txt
# License: GNU Affero General Public License v3 or later (AGPLv3+)
# See https://www.gnu.org/licenses/agpl-3.0.html

import frappe
import requests
import json
import base64
from datetime import datetime, timedelta
from frappe import _


def decode_token_payload(token):
    """
    Decodifica la seconda parte del token JWT (payload) usando base64.
    Il token JWT è composto da 3 parti separate da punti: header.payload.signature
    """
    try:
        # Estrai la seconda parte (payload) del token
        parts = token.split('.')
        if len(parts) != 3:
            frappe.log_error("Invalid token format", "Token Decode Error")
            return None

        payload = parts[1]

        # Aggiungi padding se necessario per base64
        # Base64 richiede che la lunghezza sia multipla di 4
        padding = len(payload) % 4
        if padding:
            payload += '=' * (4 - padding)

        # Decodifica base64
        decoded_bytes = base64.b64decode(payload)
        decoded_str = decoded_bytes.decode('utf-8')

        # Parse JSON
        token_data = json.loads(decoded_str)

        return token_data

    except Exception as e:
        frappe.log_error(f"Error decoding token: {str(e)}", "Token Decode Error")
        return None


@frappe.whitelist()
def generate_token(company):
    """
    Genera un nuovo token di autenticazione per l'azienda specificata.
    Il token ha una validità di 24 ore.
    """
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Prepara l'URL di login
    login_url = f"{settings.api_url.rstrip('/')}/login"

    # Prepara il payload
    payload = {
        "email": settings.email,
        "password": settings.get_password("password")
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        # Effettua la richiesta di autenticazione
        response = requests.post(login_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        # Estrai il token dalla risposta
        data = response.json()
        token = data.get("token")

        if not token:
            frappe.throw(_("Token not found in response"))

        # Decodifica la seconda parte del token (payload)
        token_details = decode_token_payload(token)

        # Calcola i timestamp
        now = datetime.now()
        expires_at = now + timedelta(hours=24)

        # Salva il token, i timestamp e i dettagli decodificati
        settings.access_token = token
        settings.token_created_at = now
        settings.token_expires_at = expires_at
        settings.token_details = json.dumps(token_details, indent=2) if token_details else None
        settings.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "success": True,
            "token": token,
            "expires_at": expires_at
        }

    except requests.exceptions.RequestException as e:
        frappe.log_error(f"OpenBanking authentication error: {str(e)}", "OpenBanking Authentication")
        frappe.throw(_("Authentication failed: {0}").format(str(e)))


def get_valid_token(company):
    """
    Restituisce un token valido per l'azienda specificata.
    Se il token è scaduto o sta per scadere (meno di 1 ora rimanente), ne genera uno nuovo.
    """
    settings = frappe.get_doc("OpenBanking Settings", company)

    # Verifica se esiste un token
    if not settings.access_token or not settings.token_expires_at:
        # Nessun token presente, generane uno nuovo
        result = generate_token(company)
        return result.get("token")

    # Verifica se il token è ancora valido (con margine di 1 ora)
    now = datetime.now()
    expiry_threshold = now + timedelta(hours=1)

    if settings.token_expires_at <= expiry_threshold:
        # Token scaduto o in scadenza, generane uno nuovo
        result = generate_token(company)
        return result.get("token")

    # Token ancora valido
    return settings.access_token


@frappe.whitelist()
def get_auth_header(company):
    """
    Restituisce l'header Authorization con un token valido.
    """
    token = get_valid_token(company)
    return {
        "Authorization": f"Bearer {token}"
    }
