// Copyright (c) 2025, Solede and contributors
// For license information, please see license.txt

/**
 * Helper functions per OpenBanking Settings
 * Centralizza le chiamate API ripetitive
 */

window.OpenBankingHelpers = {
	/**
	 * Effettua una chiamata API standard con gestione uniforme
	 *
	 * @param {string} method - Metodo API da chiamare
	 * @param {object} args - Argomenti da passare al metodo
	 * @param {string} freezeMessage - Messaggio da mostrare durante il caricamento
	 * @param {function} callback - Callback da eseguire in caso di successo
	 * @param {string} successMessage - Messaggio di successo (opzionale)
	 */
	call_api: function(method, args, freezeMessage, callback, successMessage) {
		frappe.call({
			method: method,
			args: args,
			freeze: true,
			freeze_message: __(freezeMessage),
			callback: function(r) {
				if (r.message && r.message.success) {
					if (successMessage) {
						frappe.show_alert({
							message: __(successMessage),
							indicator: "green"
						}, 5);
					} else if (r.message.message) {
						frappe.show_alert({
							message: r.message.message,
							indicator: "green"
						}, 5);
					}

					if (callback) {
						callback(r);
					}
				}
			}
		});
	},

	/**
	 * Processa account selezionati nella grid con un'operazione specifica
	 *
	 * @param {object} frm - Form object
	 * @param {function} filterFn - Funzione per filtrare gli account validi
	 * @param {string} method - Metodo API da chiamare
	 * @param {function} argsFn - Funzione che genera gli args per ogni account
	 * @param {string} confirmMsg - Messaggio di conferma (con {0} per il count)
	 * @param {string} successMsg - Messaggio di successo (con {0} per il count)
	 * @param {string} indicator - Indicatore colore (green, orange, red)
	 */
	process_selected_accounts: function(frm, filterFn, method, argsFn, confirmMsg, successMsg, indicator) {
		const selected = frm.fields_dict.accounts.grid.get_selected();

		if (selected.length === 0) {
			frappe.msgprint(__('Please select at least one account'));
			return;
		}

		const accounts = frm.doc.accounts.filter(acc =>
			selected.includes(acc.name) && filterFn(acc)
		);

		if (accounts.length === 0) {
			frappe.msgprint(__('No valid accounts selected'));
			return;
		}

		frappe.confirm(
			__(confirmMsg, [accounts.length]),
			() => {
				let completed = 0;
				accounts.forEach(acc => {
					frappe.call({
						method: method,
						args: argsFn(frm.doc.company, acc),
						callback: function(r) {
							completed++;
							if (completed === accounts.length) {
								frappe.show_alert({
									message: __(successMsg, [accounts.length]),
									indicator: indicator || "green"
								}, 3);
								frm.reload_doc();
							}
						}
					});
				});
			}
		);
	},

	/**
	 * Abilita account selezionati
	 */
	enable_selected_accounts: function(frm) {
		this.process_selected_accounts(
			frm,
			acc => !acc.enabled,
			"solede_openbanking.api.business_registry.toggle_account",
			(company, acc) => ({ company: company, uuid: acc.uuid, enabled: 1 }),
			"Enable {0} selected account(s)?",
			"Enabled {0} account(s)",
			"green"
		);
	},

	/**
	 * Disabilita account selezionati
	 */
	disable_selected_accounts: function(frm) {
		this.process_selected_accounts(
			frm,
			acc => acc.enabled,
			"solede_openbanking.api.business_registry.toggle_account",
			(company, acc) => ({ company: company, uuid: acc.uuid, enabled: 0 }),
			"Disabling will clear balance, extra data, and transactions. Disable {0} selected account(s)?",
			"Disabled {0} account(s)",
			"orange"
		);
	},

	/**
	 * Trova e mostra dettagli di un account per nome
	 */
	show_account_details_by_name: function(frm, account_name) {
		const account = frm.doc.accounts.find(acc => acc.name === account_name);
		if (account) {
			this.show_account_details(account);
		}
	},

	/**
	 * Mostra dettagli completi account in un modal
	 */
	show_account_details: function(account_row) {
		if (!account_row.raw_data) {
			frappe.msgprint(__('No detailed data available for this account'));
			return;
		}

		try {
			const data = JSON.parse(account_row.raw_data);

			// Costruisci HTML con tutti i dettagli
			let html = '<div class="account-details">';

			// Sezione principale
			html += '<h5>' + __('Account Information') + '</h5>';
			html += '<table class="table table-bordered table-sm">';
			html += `<tr><th style="width: 30%">${__('UUID')}</th><td>${data.uuid || ''}</td></tr>`;
			html += `<tr><th>${__('Account ID')}</th><td>${data.accountId || ''}</td></tr>`;
			html += `<tr><th>${__('IBAN')}</th><td>${account_row.iban || ''}</td></tr>`;
			html += `<tr><th>${__('Account Name')}</th><td>${data.name || ''}</td></tr>`;
			html += `<tr><th>${__('Bank')}</th><td>${account_row.bank_display || ''}</td></tr>`;
			html += `<tr><th>${__('Country')}</th><td>${data.providerCountry || ''}</td></tr>`;
			html += `<tr><th>${__('Nature')}</th><td>${data.nature || ''}</td></tr>`;
			html += `<tr><th>${__('Balance')}</th><td><strong>${account_row.balance_display || 'N/A'}</strong></td></tr>`;
			html += `<tr><th>${__('Enabled')}</th><td>${account_row.enabled ? 'Yes' : 'No'}</td></tr>`;
			html += `<tr><th>${__('Consent Expires')}</th><td>${data.consentExpiresAt || 'N/A'}</td></tr>`;

			// Altri identificatori
			if (data.bban || data.swift || data.accountNumber) {
				html += `<tr><th>${__('BBAN')}</th><td>${data.bban || 'N/A'}</td></tr>`;
				html += `<tr><th>${__('SWIFT')}</th><td>${data.swift || 'N/A'}</td></tr>`;
				html += `<tr><th>${__('Account Number')}</th><td>${data.accountNumber || 'N/A'}</td></tr>`;
			}

			html += '</table>';

			// Sezione Extra data (mostrata come JSON formattato, senza parsing specifico)
			if (data.extra && Object.keys(data.extra).length > 0) {
				html += '<h5 class="mt-3">' + __('Additional Information') + '</h5>';
				html += '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; max-height: 300px; overflow-y: auto;">';
				html += JSON.stringify(data.extra, null, 2);
				html += '</pre>';
			}

			// Sezione Systems
			if (data.systems && data.systems.length > 0) {
				html += '<h5 class="mt-3">' + __('Supported Systems') + '</h5>';
				html += '<p>' + data.systems.join(', ').toUpperCase() + '</p>';
			}

			html += '</div>';

			// Mostra il modal
			frappe.msgprint({
				title: __('Account Details: {0}', [account_row.bank_display || data.accountId]),
				message: html,
				indicator: 'blue',
				wide: true
			});

		} catch (e) {
			frappe.msgprint(__('Error parsing account data: {0}', [e.message]));
		}
	},

	/**
	 * Elimina account selezionati
	 */
	delete_selected_accounts: function(frm) {
		const selected = frm.fields_dict.accounts.grid.get_selected();

		if (selected.length === 0) {
			frappe.msgprint(__('Please select at least one account'));
			return;
		}

		const accounts_to_delete = frm.doc.accounts.filter(acc =>
			selected.includes(acc.name)
		);
		const enabled_accounts = accounts_to_delete.filter(acc => acc.enabled);

		if (enabled_accounts.length > 0) {
			frappe.msgprint(__('Cannot delete enabled accounts. Please disable them first.'));
			return;
		}

		frappe.confirm(
			__('WARNING: This will delete the selected account(s) AND all other accounts from the same bank connection(s).<br><br>All accounts in the same connection must be disabled before deletion.<br><br>Delete {0} selected account(s)?', [accounts_to_delete.length]),
			() => {
				let completed = 0;
				accounts_to_delete.forEach(acc => {
					frappe.call({
						method: "solede_openbanking.api.business_registry.delete_account",
						args: {
							company: frm.doc.company,
							uuid: acc.uuid
						},
						callback: function(r) {
							completed++;
							if (completed === accounts_to_delete.length) {
								frappe.show_alert({
									message: __('Deleted {0} account(s)', [accounts_to_delete.length]),
									indicator: "red"
								}, 3);
								frm.reload_doc();
							}
						}
					});
				});
			}
		);
	}
};
