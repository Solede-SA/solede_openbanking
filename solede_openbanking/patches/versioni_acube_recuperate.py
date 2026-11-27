"""Le versioni già ricevute da ACube che l'importazione di allora non ha usato. Il movimento in attesa la cui versione
contabilizzata è arrivata dopo passa a contabilizzato (`contabilizza`, come fa oggi l'importazione). La commissione di
cambio Revolut finita fra le ricezioni del pagamento, perché prima della regola `:fee` aveva il suo stesso
identificativo, diventa il suo registro e il suo movimento, come li crea oggi l'importazione: le spese bancarie la
registrano poi con la loro regola nel giro orario."""

import frappe

from solede_openbanking.api.business_registry import (
	contabilizza,
	create_bank_transaction_from_acube,
	create_transaction_log,
	extract_unique_transaction_id,
	movimenti_ricevuti,
)

REGISTRO = "ACube Transaction Log"


def execute():
	for nome in frappe.get_all(REGISTRO, pluck="name"):
		recupera(nome)


def recupera(nome):
	log = frappe.db.get_value(
		REGISTRO, nome, ["company", "bank_account", "acube_account_uuid", "acube_transaction_id", "bank_transaction"], as_dict=True,
	)
	for movimento in movimenti_ricevuti(nome):
		identificativo = extract_unique_transaction_id(movimento)
		if identificativo == log.acube_transaction_id:
			if log.bank_transaction:
				contabilizza(log.bank_transaction, movimento, nome)
		elif not frappe.db.exists(REGISTRO, {"acube_transaction_id": identificativo}) and not frappe.db.exists(
			"Bank Transaction", {"acube_transaction_id": identificativo, "docstatus": ["<", 2]}
		):
			nuovo = create_transaction_log(log.company, log.acube_account_uuid, movimento, log.bank_account)
			create_bank_transaction_from_acube(log.company, log.bank_account, movimento, nuovo.name)
