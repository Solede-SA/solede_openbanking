// Copyright (c) 2025, Solede and contributors
// For license information, please see license.txt

frappe.ui.form.on('Supplier', {
	refresh: function(frm) {
		if (!frm.is_new()) {
			// Aggiungi bottone per creare Bank Account da IBAN
			frm.add_custom_button(__('Crea conto da IBAN'), function() {
				show_iban_dialog(frm);
			}, __('Bank Account'));
		}
	}
});

function show_iban_dialog(frm) {
	let dialog = new frappe.ui.Dialog({
		title: __('Crea Bank Account da IBAN'),
		fields: [
			{
				fieldname: 'iban',
				fieldtype: 'Data',
				label: __('IBAN'),
				reqd: 1,
				description: __('Inserisci l\'IBAN del fornitore (es: IT60X0542811101000000123456)')
			},
			{
				fieldname: 'account_name',
				fieldtype: 'Data',
				label: __('Nome Account (opzionale)'),
				description: __('Se vuoto, verrà generato automaticamente')
			},
			{
				fieldname: 'validation_section',
				fieldtype: 'Section Break',
				label: __('Validazione IBAN')
			},
			{
				fieldname: 'validation_html',
				fieldtype: 'HTML'
			}
		],
		primary_action_label: __('Crea Bank Account'),
		primary_action: function(values) {
			create_bank_account(values, dialog, frm);
		}
	});

	// Aggiungi validazione real-time dell'IBAN
	dialog.fields_dict.iban.$input.on('blur', function() {
		let iban = dialog.get_value('iban');
		if (iban) {
			validate_iban_realtime(iban, dialog, frm);
		}
	});

	dialog.show();
}

function create_bank_account(values, dialog, frm) {
	if (!values.iban) {
		frappe.msgprint(__('IBAN è obbligatorio'));
		return;
	}

	frappe.call({
		method: 'solede_openbanking.api.iban_enrichment.create_bank_and_account_from_iban',
		args: {
			iban: values.iban,
			party_type: 'Supplier',
			party: frm.doc.name,
			account_name: values.account_name
		},
		freeze: true,
		freeze_message: __('Creazione Bank Account in corso...'),
		callback: function(r) {
			if (r.message) {
				frappe.show_alert({
					message: __('Bank Account creato con successo: {0}', [r.message.name]),
					indicator: 'green'
				}, 5);
				dialog.hide();
				frm.reload_doc();
			}
		},
		error: function(r) {
			frappe.msgprint({
				title: __('Errore'),
				message: r.message || __('Errore durante la creazione del Bank Account'),
				indicator: 'red'
			});
		}
	});
}

function validate_iban_realtime(iban, dialog, frm) {
	frappe.call({
		method: 'solede_openbanking.api.iban_enrichment.validate_iban_api',
		args: {
			iban: iban,
			party_type: 'Supplier',
			party: frm.doc.name
		},
		callback: function(r) {
			if (r.message) {
				let html = '';
				if (r.message.valid) {
					let bank_info = r.message.bank_info;

					if (r.message.already_exists) {
						// Account già esistente - mostra warning arancione
						html = `
							<div class="alert alert-warning">
								<strong><i class="fa fa-exclamation-triangle"></i> Bank Account già esistente</strong>
								<p style="margin-top: 5px; margin-bottom: 0;">${r.message.message}</p>
								<ul style="margin-top: 10px; margin-bottom: 0;">
									<li><strong>Banca:</strong> ${bank_info.bank_name || 'Non disponibile'}</li>
									<li><strong>Paese:</strong> ${bank_info.country_code || 'Non disponibile'}</li>
								</ul>
							</div>
						`;

						// Cambia il bottone per aprire l'account esistente
						dialog.set_primary_action(__('Apri Bank Account esistente'), function() {
							frappe.set_route('Form', 'Bank Account', r.message.account_name);
							dialog.hide();
						});
					} else {
						// IBAN valido ma non esiste ancora
						html = `
							<div class="alert alert-success">
								<strong><i class="fa fa-check-circle"></i> IBAN Valido</strong>
								<ul style="margin-top: 10px; margin-bottom: 0;">
									<li><strong>Banca:</strong> ${bank_info.bank_name || 'Non disponibile'}</li>
									<li><strong>SWIFT/BIC:</strong> ${bank_info.swift_number || 'Non disponibile'}</li>
									<li><strong>Paese:</strong> ${bank_info.country_code || 'Non disponibile'}</li>
								</ul>
							</div>
						`;

						// Ripristina il bottone di creazione originale
						dialog.set_primary_action(__('Crea Bank Account'), function() {
							create_bank_account(dialog.get_values(), dialog, frm);
						});
					}
				} else {
					html = `
						<div class="alert alert-danger">
							<strong><i class="fa fa-times-circle"></i> IBAN Non Valido</strong>
							<p style="margin-top: 5px; margin-bottom: 0;">${r.message.message}</p>
						</div>
					`;
				}
				dialog.fields_dict.validation_html.$wrapper.html(html);
			}
		}
	});
}
