# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt


def azzera_data_di_liquidazione_su_rettifica(doc, method=None):
	"""Payment Entry, before_save: Frappe ignora no_copy nella rettifica (amend) e copia clearance_date dal pagamento
	originale; il pagamento nuovo non è collegato a nessun movimento bancario, quindi la data va vuota."""
	if doc.amended_from:
		doc.clearance_date = None
