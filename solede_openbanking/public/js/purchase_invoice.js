// Copyright (c) 2025, Solede and contributors
// For license information, please see license.txt

frappe.ui.form.on('Purchase Invoice', {
	refresh: function(frm) {
		// Mostra bottone solo se:
		// 1. Documento è submitted
		// 2. C'è ancora un outstanding_amount
		// 3. NON esiste già un pagamento OpenBanking in corso
		if (frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0 && !frm.doc.openbanking_payment) {
			frm.add_custom_button(__('Esegui Bonifico'), function() {
				initiate_payment_flow(frm);
			}, __('OpenBanking'));
		}

		// Mostra status pagamento se esiste
		if (frm.doc.openbanking_payment) {
			show_payment_status(frm);
		}
	}
});

function initiate_payment_flow(frm) {
	// Step 1: Recupera Bank Account del fornitore
	frappe.call({
		method: 'solede_openbanking.api.payments.get_supplier_bank_accounts',
		args: {
			supplier_name: frm.doc.supplier
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				// Fornitore ha già Bank Account
				show_payment_dialog(frm, r.message);
			} else {
				// Fornitore non ha Bank Account, chiedi IBAN
				show_iban_input_dialog(frm);
			}
		}
	});
}

function show_payment_dialog(frm, supplier_accounts) {
	// Recupera account OpenBanking della company
	frappe.call({
		method: 'solede_openbanking.api.payments.get_company_openbanking_accounts',
		args: {
			company: frm.doc.company
		},
		callback: function(r) {
			if (!r.message || r.message.length === 0) {
				frappe.msgprint({
					title: __('Errore'),
					message: __('Nessun account OpenBanking configurato per la company {0}', [frm.doc.company]),
					indicator: 'red'
				});
				return;
			}

			let company_accounts = r.message;

			// Prepara opzioni per select supplier account
			let supplier_account_options = supplier_accounts.map(acc => {
				let label = acc.account_name;
				if (acc.iban) {
					label += ` (${acc.iban})`;
				}
				if (acc.is_default) {
					label += ' [Default]';
				}
				return {
					label: label,
					value: acc.iban
				};
			});

			// Aggiungi opzione per nuovo IBAN
			supplier_account_options.push({
				label: __('+ Nuovo IBAN'),
				value: '__new__'
			});

			// Prepara opzioni per select company account con indicatori capabilities
			let company_account_options = company_accounts.map(acc => {
				let label = `${acc.bank_display} - ${acc.iban}`;

				if (acc.has_payment_support) {
					// Account con supporto pagamenti - mostra capabilities
					let caps = [];
					if (acc.capabilities.sepa) caps.push('SEPA');
					if (acc.capabilities.sepa_instant) caps.push('Instant');
					if (caps.length > 0) {
						label += ` [${caps.join(', ')}]`;
					}
				} else {
					// Account SENZA supporto pagamenti - warning
					label += ' [⚠️ Solo lettura]';
				}

				return {
					label: label,
					value: acc.uuid,
					capabilities: acc.capabilities || {sepa: false, sepa_instant: false},
					has_payment_support: acc.has_payment_support || false
				};
			});

			// Dialog principale
			let dialog = new frappe.ui.Dialog({
				title: __('Esegui Bonifico SEPA'),
				fields: [
					{
						fieldname: 'payment_section',
						fieldtype: 'Section Break',
						label: __('Dettagli Pagamento')
					},
					{
						fieldname: 'amount',
						fieldtype: 'Currency',
						label: __('Importo'),
						default: frm.doc.outstanding_amount,
						read_only: 1
					},
					{
						fieldname: 'description',
						fieldtype: 'Data',
						label: __('Descrizione'),
						default: `Pagamento ${frm.doc.name}`,
						read_only: 1
					},
					{
						fieldname: 'col_break_1',
						fieldtype: 'Column Break'
					},
					{
						fieldname: 'use_instant',
						fieldtype: 'Check',
						label: __('Bonifico Istantaneo (SEPA Instant)'),
						description: __('Il pagamento sarà elaborato in pochi secondi (max 100.000 EUR)')
					},
					{
						fieldname: 'account_section',
						fieldtype: 'Section Break',
						label: __('Conti Bancari')
					},
					{
						fieldname: 'company_account',
						fieldtype: 'Select',
						label: __('Conto da cui pagare'),
						options: company_account_options,
						reqd: 1
					},
					{
						fieldname: 'col_break_2',
						fieldtype: 'Column Break'
					},
					{
						fieldname: 'supplier_account',
						fieldtype: 'Select',
						label: __('IBAN Fornitore'),
						options: supplier_account_options,
						reqd: 1
					}
				],
				primary_action_label: __('Avvia Bonifico'),
				primary_action: function(values) {
					// Se selezionato "Nuovo IBAN"
					if (values.supplier_account === '__new__') {
						dialog.hide();
						show_iban_input_dialog(frm);
						return;
					}

					// Procedi con il pagamento
					execute_payment(frm, values, dialog);
				}
			});

			dialog.show();
		}
	});
}

function show_iban_input_dialog(frm) {
	// DRY: Riutilizzo logica esistente da supplier.js
	let dialog = new frappe.ui.Dialog({
		title: __('Inserisci IBAN Fornitore'),
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
		primary_action_label: __('Crea e Continua'),
		primary_action: function(values) {
			create_bank_account_and_continue(values, dialog, frm);
		}
	});

	// Validazione real-time IBAN (DRY: riutilizzo logica esistente)
	dialog.fields_dict.iban.$input.on('blur', function() {
		let iban = dialog.get_value('iban');
		if (iban) {
			validate_iban_for_payment(iban, dialog, frm);
		}
	});

	dialog.show();
}

function validate_iban_for_payment(iban, dialog, frm) {
	frappe.call({
		method: 'solede_openbanking.api.iban_enrichment.validate_iban_api',
		args: {
			iban: iban,
			party_type: 'Supplier',
			party: frm.doc.supplier
		},
		callback: function(r) {
			if (r.message) {
				let html = '';
				if (r.message.valid) {
					let bank_info = r.message.bank_info;

					if (r.message.already_exists) {
						html = `
							<div class="alert alert-warning">
								<strong><i class="fa fa-exclamation-triangle"></i> Bank Account già esistente</strong>
								<p style="margin-top: 5px; margin-bottom: 0;">${r.message.message}</p>
							</div>
						`;

						// Cambia azione: usa account esistente
						dialog.set_primary_action(__('Usa Account Esistente'), function() {
							dialog.hide();
							// Ricarica dialog principale con account esistente
							initiate_payment_flow(frm);
						});
					} else {
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

function create_bank_account_and_continue(values, dialog, frm) {
	if (!values.iban) {
		frappe.msgprint(__('IBAN è obbligatorio'));
		return;
	}

	frappe.call({
		method: 'solede_openbanking.api.payments.create_or_get_supplier_bank_account',
		args: {
			supplier_name: frm.doc.supplier,
			iban: values.iban,
			account_name: values.account_name
		},
		freeze: true,
		freeze_message: __('Creazione Bank Account in corso...'),
		callback: function(r) {
			if (r.message) {
				frappe.show_alert({
					message: __('Bank Account creato con successo'),
					indicator: 'green'
				}, 3);
				dialog.hide();
				// Ricarica flow principale
				initiate_payment_flow(frm);
			}
		}
	});
}

function execute_payment(frm, values, dialog) {
	// Trova il nome del creditor dall'IBAN selezionato
	let creditor_name = frm.doc.supplier_name;

	frappe.call({
		method: 'solede_openbanking.api.payments.initiate_sepa_payment',
		args: {
			reference_doctype: 'Purchase Invoice',
			reference_name: frm.doc.name,
			account_uuid: values.company_account,
			creditor_iban: values.supplier_account,
			creditor_name: creditor_name,
			use_instant: values.use_instant ? 1 : 0
		},
		freeze: true,
		freeze_message: __('Avvio bonifico in corso...'),
		callback: function(r) {
			if (r.message && r.message.connect_url) {
				dialog.hide();

				// Mostra messaggio di successo
				frappe.msgprint({
					title: __('Bonifico Avviato'),
					message: __('Il bonifico è stato avviato. Verrai reindirizzato alla banca per autorizzare il pagamento.'),
					indicator: 'green'
				});

				// Salva payment_name nel documento (per reference)
				frm.set_value('openbanking_payment', r.message.payment_name);
				frm.save();

				// Apri connect_url in nuova finestra
				setTimeout(function() {
					window.open(r.message.connect_url, '_blank', 'width=800,height=600');
				}, 2000);

				// Refresh form per mostrare status
				frm.reload_doc();
			}
		}
	});
}

function show_payment_status(frm) {
	// Mostra badge con status pagamento
	frappe.call({
		method: 'frappe.client.get_value',
		args: {
			doctype: 'OpenBanking Payment',
			filters: { name: frm.doc.openbanking_payment },
			fieldname: ['status', 'system', 'uuid']
		},
		callback: function(r) {
			if (r.message) {
				let status = r.message.status;
				let indicator = 'blue';

				if (status === 'completed') {
					indicator = 'green';
				} else if (status === 'failed') {
					indicator = 'red';
				} else if (status === 'processing') {
					indicator = 'orange';
				}

				frm.dashboard.add_indicator(__('Pagamento: {0}', [status.toUpperCase()]), indicator);

				// Bottone per refresh status
				frm.add_custom_button(__('Aggiorna Status Pagamento'), function() {
					refresh_payment_status(frm, r.message.uuid);
				}, __('OpenBanking'));
			}
		}
	});
}

function refresh_payment_status(frm, payment_uuid) {
	frappe.call({
		method: 'solede_openbanking.api.payments.get_payment_status',
		args: {
			payment_uuid: payment_uuid
		},
		freeze: true,
		freeze_message: __('Aggiornamento status in corso...'),
		callback: function(r) {
			if (r.message) {
				frappe.show_alert({
					message: __('Status aggiornato: {0}', [r.message.new_status]),
					indicator: 'blue'
				}, 5);
				frm.reload_doc();
			}
		}
	});
}
