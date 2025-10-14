# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _
from solede_openbanking.api.authentication import get_valid_token
from solede_openbanking.api.utils import handle_api_error, debug_log, validate_company_settings


class ACubeAPIClient:
	"""
	Client per gestire le chiamate alle API ACube Open Banking.
	Centralizza autenticazione, headers, gestione errori e logging.
	"""

	def __init__(self, company):
		"""
		Inizializza il client per un'azienda specifica.

		Args:
			company: Nome della company
		"""
		self.company = company
		self.settings, self.company_doc, self.fiscal_id = validate_company_settings(company)
		self.token = get_valid_token(company)

	def build_url(self, path):
		"""
		Costruisce URL completo per un endpoint.

		Args:
			path: Path relativo dell'endpoint

		Returns:
			str: URL completo
		"""
		return f"{self.settings.openbanking_api_url.rstrip('/')}/{path}"

	def get_headers(self, include_content_type=True):
		"""
		Restituisce gli headers standard per le richieste.

		Args:
			include_content_type: Se includere Content-Type header

		Returns:
			dict: Headers per la richiesta
		"""
		headers = {"Authorization": f"Bearer {self.token}"}
		if include_content_type:
			headers["Content-Type"] = "application/json"
		return headers

	def make_request(self, method, endpoint_path, operation_name,
					 expected_status_codes=None, debug=True, **kwargs):
		"""
		Effettua una richiesta API con gestione errori uniforme.

		Args:
			method: Metodo HTTP (GET, POST, PUT, DELETE)
			endpoint_path: Path dell'endpoint
			operation_name: Nome operazione per log e errori
			expected_status_codes: Lista di status code considerati successo (default: [200, 201, 202])
			debug: Se stampare log di debug
			**kwargs: Parametri aggiuntivi per requests (json, params, etc.)

		Returns:
			dict: Response JSON se successo
		"""
		if expected_status_codes is None:
			expected_status_codes = [200, 201, 202]

		url = self.build_url(endpoint_path)

		# Log di debug
		if debug:
			debug_params = {
				"Method": method,
				"URL": url,
				"Token": self.token
			}
			if 'json' in kwargs:
				debug_params["Payload"] = kwargs['json']
			if 'params' in kwargs:
				debug_params["Params"] = kwargs['params']
			debug_log(operation_name, **debug_params)

		try:
			response = requests.request(method, url, timeout=30, **kwargs)

			# Log response
			if debug:
				print(f"Response Status Code: {response.status_code}")
				if response.text:
					print(f"Response Body (first 500 chars): {response.text[:500]}")

			# Verifica status code
			if response.status_code in expected_status_codes:
				return response.json()
			else:
				handle_api_error(response, url, operation_name)

		except requests.exceptions.RequestException as e:
			error_msg = str(e)
			frappe.log_error(f"URL: {url}, Error: {error_msg}", f"{operation_name} API Error")
			frappe.throw(_("Failed to connect to Business Registry API: {0}").format(error_msg))

	def get(self, endpoint_path, operation_name, **kwargs):
		"""
		Effettua una richiesta GET.

		Args:
			endpoint_path: Path dell'endpoint
			operation_name: Nome operazione
			**kwargs: Parametri aggiuntivi

		Returns:
			dict: Response JSON
		"""
		headers = self.get_headers(include_content_type=False)
		return self.make_request("GET", endpoint_path, operation_name, headers=headers, **kwargs)

	def post(self, endpoint_path, operation_name, payload=None, **kwargs):
		"""
		Effettua una richiesta POST.

		Args:
			endpoint_path: Path dell'endpoint
			operation_name: Nome operazione
			payload: Dati JSON da inviare
			**kwargs: Parametri aggiuntivi

		Returns:
			dict: Response JSON
		"""
		headers = self.get_headers(include_content_type=True)
		return self.make_request("POST", endpoint_path, operation_name,
								 json=payload, headers=headers, **kwargs)

	def put(self, endpoint_path, operation_name, payload=None, **kwargs):
		"""
		Effettua una richiesta PUT.

		Args:
			endpoint_path: Path dell'endpoint
			operation_name: Nome operazione
			payload: Dati JSON da inviare
			**kwargs: Parametri aggiuntivi

		Returns:
			dict: Response JSON
		"""
		headers = self.get_headers(include_content_type=True)
		return self.make_request("PUT", endpoint_path, operation_name,
								 json=payload, headers=headers, **kwargs)

	def delete(self, endpoint_path, operation_name, **kwargs):
		"""
		Effettua una richiesta DELETE.

		Args:
			endpoint_path: Path dell'endpoint
			operation_name: Nome operazione
			**kwargs: Parametri aggiuntivi

		Returns:
			dict: Response JSON
		"""
		headers = self.get_headers(include_content_type=False)
		return self.make_request("DELETE", endpoint_path, operation_name, headers=headers, **kwargs)
