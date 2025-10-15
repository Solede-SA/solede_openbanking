// Copyright (c) 2025, Solede and contributors
// For license information, please see license.txt

frappe.ui.form.on('Bank Transaction', {
	refresh: function(frm) {
		// Mostra il bottone solo se la transazione proviene da ACube ed è submitted
		if (frm.doc.api_source === 'ACube' && frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Annulla Transazione Duplicata'), function() {
				frappe.confirm(
					__('Sei sicuro di voler annullare questa transazione? Questa azione è irreversibile.<br><br>La transazione verrà cancellata e rimossa dalla riconciliazione.'),
					function() {
						// Utente ha confermato
						frappe.call({
							method: 'solede_openbanking.api.business_registry.cancel_duplicate_transaction',
							args: {
								bank_transaction: frm.doc.name
							},
							freeze: true,
							freeze_message: __('Annullamento transazione in corso...'),
							callback: function(r) {
								if (r.message && r.message.success) {
									frappe.show_alert({
										message: __('Transazione annullata con successo'),
										indicator: 'green'
									}, 5);

									// Torna alla lista delle Bank Transaction
									frappe.set_route('List', 'Bank Transaction');
								}
							}
						});
					}
				);
			}, __('Azioni'));
		}
	}
});
