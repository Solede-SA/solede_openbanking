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
