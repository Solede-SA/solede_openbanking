"""Registro ACube e impostazioni OpenBanking si aggiornano da soli: lo storico è spento nei DocType, si tolgono le versioni già accumulate."""

import frappe


def execute():
	frappe.db.delete("Version", {"ref_doctype": ["in", ["ACube Transaction Log", "OpenBanking Settings"]]})
