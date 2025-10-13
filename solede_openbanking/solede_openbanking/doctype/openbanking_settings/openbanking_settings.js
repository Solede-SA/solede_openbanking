// Copyright (c) 2025, Solede and contributors
// For license information, please see license.txt

frappe.ui.form.on("OpenBanking Settings", {
    refresh(frm) {
        if (!frm.is_new()) {
            // Nascondi il bottone Delete standard della child table accounts
            // Prova diversi selettori CSS
            if (!$('#hide-accounts-delete-btn').length) {
                $('<style id="hide-accounts-delete-btn">')
                    .text(`
                        [data-fieldname="accounts"] .grid-delete-multiple-rows { display: none !important; }
                        [data-fieldname="accounts"] .btn-open-row { display: none !important; }
                        [data-fieldname="accounts"] .grid-footer .btn-danger { display: none !important; }
                    `)
                    .appendTo('head');
            }

            // Aggiungi anche un timeout per nascondere dopo il rendering
            setTimeout(() => {
                if (frm.fields_dict.accounts && frm.fields_dict.accounts.grid) {
                    frm.fields_dict.accounts.grid.wrapper.find('.btn-danger').hide();
                    frm.fields_dict.accounts.grid.wrapper.find('.grid-delete-multiple-rows').hide();
                }
            }, 500);
            // Bottone per generare il token
            frm.add_custom_button(__("Generate Token"), () => {
                frappe.call({
                    method: "solede_openbanking.api.authentication.generate_token",
                    args: {
                        company: frm.doc.company
                    },
                    freeze: true,
                    freeze_message: __("Generating authentication token..."),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __("Token generated successfully"),
                                indicator: "green"
                            }, 5);
                            frm.reload_doc();
                        }
                    }
                });
            });

            // Bottone per creare Business Registry (solo se non ancora creato)
            if (!frm.doc.business_registry_created) {
                frm.add_custom_button(__("Create Business Registry"), () => {
                    frappe.confirm(
                        __('Creating a Business Registry will incur a fee. Do you want to continue?'),
                        () => {
                            frappe.call({
                                method: "solede_openbanking.api.business_registry.create_business_registry",
                                args: {
                                    company: frm.doc.company,
                                    password: "" // Non più usata
                                },
                                freeze: true,
                                freeze_message: __("Creating Business Registry..."),
                                callback: function(r) {
                                    if (r.message && r.message.success) {
                                        frappe.show_alert({
                                            message: __("Business Registry created successfully"),
                                            indicator: "green"
                                        }, 5);
                                        frm.reload_doc();
                                    }
                                }
                            });
                        }
                    );
                });
            }

            // Bottone per avviare la connessione bancaria
            if (frm.doc.business_registry_created) {
                frm.add_custom_button(__("Connect Bank Account"), () => {
                    // Genera automaticamente il return URL usando l'URL del doctype corrente
                    const return_url = window.location.origin + window.location.pathname;

                    // Verifica se siamo in un sito .local per mostrare l'opzione test
                    const is_local_site = window.location.hostname.endsWith('.local') ||
                                         window.location.hostname === 'localhost';

                    let fields = [
                        {
                            fieldname: 'bank_manager_email',
                            fieldtype: 'Data',
                            label: __('Bank Manager Email (optional)'),
                            description: __('Email of the person managing the connection')
                        },
                        {
                            fieldname: 'days',
                            fieldtype: 'Int',
                            label: __('Consent Days'),
                            default: 180,
                            description: __('Number of days for which to grant consent (1-180)')
                        }
                    ];

                    // Aggiungi campo test_mode solo se siamo su .local
                    if (is_local_site) {
                        fields.push({
                            fieldname: 'test_mode',
                            fieldtype: 'Check',
                            label: __('Test Mode (Fake Bank)'),
                            default: 0,
                            description: __('Use XF country code to connect to a simulated test bank (no real credentials needed)')
                        });
                    }

                    frappe.prompt(fields, (values) => {
                        frappe.call({
                            method: "solede_openbanking.api.business_registry.start_connect_request",
                            args: {
                                company: frm.doc.company,
                                return_url: return_url,
                                bank_manager_email: values.bank_manager_email || null,
                                days: values.days || 180,
                                test_mode: values.test_mode || 0
                            },
                            freeze: true,
                            freeze_message: __("Creating connect request..."),
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    // Apri l'URL in una nuova finestra
                                    window.open(r.message.connect_url, '_blank');

                                    frappe.msgprint({
                                        title: __('Bank Connection'),
                                        message: __('A new window has been opened. Please complete the bank connection process there.<br><br>Connect URL: <a href="{0}" target="_blank">{0}</a>', [r.message.connect_url]),
                                        indicator: 'green'
                                    });
                                }
                            }
                        });
                    }, __('Connect Bank Account'), __('Connect'));
                });

                // Bottone per recuperare gli account autorizzati
                frm.add_custom_button(__("Refresh Accounts"), () => {
                    frappe.call({
                        method: "solede_openbanking.api.business_registry.get_accounts",
                        args: {
                            company: frm.doc.company
                        },
                        freeze: true,
                        freeze_message: __("Retrieving accounts..."),
                        callback: function(r) {
                            if (r.message && r.message.success) {
                                frappe.show_alert({
                                    message: r.message.message,
                                    indicator: "green"
                                }, 5);
                                frm.reload_doc();
                            }
                        }
                    });
                });
            }

            // Aggiungi bottoni per gestire gli account selezionati
            if (frm.doc.accounts && frm.doc.accounts.length > 0) {
                // Bottone Enable per account selezionati
                frm.fields_dict.accounts.grid.add_custom_button(__('Enable Selected'), function() {
                    const selected = frm.fields_dict.accounts.grid.get_selected();
                    if (selected.length === 0) {
                        frappe.msgprint(__('Please select at least one account'));
                        return;
                    }

                    // get_selected() restituisce i nomi delle righe, non gli indici
                    const accounts_to_enable = frm.doc.accounts.filter(acc =>
                        selected.includes(acc.name) && !acc.enabled
                    );

                    if (accounts_to_enable.length === 0) {
                        frappe.msgprint(__('All selected accounts are already enabled'));
                        return;
                    }

                    frappe.confirm(
                        __('Enable {0} selected account(s)?', [accounts_to_enable.length]),
                        () => {
                            let completed = 0;
                            accounts_to_enable.forEach(acc => {
                                frappe.call({
                                    method: "solede_openbanking.api.business_registry.toggle_account",
                                    args: {
                                        company: frm.doc.company,
                                        uuid: acc.uuid,
                                        enabled: 1
                                    },
                                    callback: function(r) {
                                        completed++;
                                        if (completed === accounts_to_enable.length) {
                                            frappe.show_alert({
                                                message: __('Enabled {0} account(s)', [accounts_to_enable.length]),
                                                indicator: "green"
                                            }, 3);
                                            frm.reload_doc();
                                        }
                                    }
                                });
                            });
                        }
                    );
                });

                // Bottone Disable per account selezionati
                frm.fields_dict.accounts.grid.add_custom_button(__('Disable Selected'), function() {
                    console.log('Disable Selected clicked');
                    const selected = frm.fields_dict.accounts.grid.get_selected();
                    console.log('Selected rows:', selected);

                    if (selected.length === 0) {
                        frappe.msgprint(__('Please select at least one account'));
                        return;
                    }

                    // get_selected() restituisce i nomi delle righe, non gli indici
                    const accounts_to_disable = frm.doc.accounts.filter(acc =>
                        selected.includes(acc.name) && acc.enabled
                    );

                    console.log('Accounts to disable:', accounts_to_disable);

                    if (accounts_to_disable.length === 0) {
                        frappe.msgprint(__('All selected accounts are already disabled'));
                        return;
                    }

                    frappe.confirm(
                        __('Disabling will clear balance, extra data, and transactions. Disable {0} selected account(s)?', [accounts_to_disable.length]),
                        () => {
                            let completed = 0;
                            accounts_to_disable.forEach(acc => {
                                frappe.call({
                                    method: "solede_openbanking.api.business_registry.toggle_account",
                                    args: {
                                        company: frm.doc.company,
                                        uuid: acc.uuid,
                                        enabled: 0
                                    },
                                    callback: function(r) {
                                        completed++;
                                        if (completed === accounts_to_disable.length) {
                                            frappe.show_alert({
                                                message: __('Disabled {0} account(s)', [accounts_to_disable.length]),
                                                indicator: "orange"
                                            }, 3);
                                            frm.reload_doc();
                                        }
                                    }
                                });
                            });
                        }
                    );
                });

                // Bottone Delete per account selezionati (solo se disabilitati)
                frm.fields_dict.accounts.grid.add_custom_button(__('Delete Selected'), function() {
                    const selected = frm.fields_dict.accounts.grid.get_selected();
                    if (selected.length === 0) {
                        frappe.msgprint(__('Please select at least one account'));
                        return;
                    }

                    // get_selected() restituisce i nomi delle righe, non gli indici
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
                });
            }

            // Bottone per recuperare i dati del Business Registry
            frm.add_custom_button(__("Get Business Registry Info"), () => {
                frappe.call({
                    method: "solede_openbanking.api.business_registry.get_business_registry_info",
                    args: {
                        company: frm.doc.company
                    },
                    freeze: true,
                    freeze_message: __("Retrieving Business Registry info..."),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            // Mostra i dati in un dialog
                            let data = r.message.data;
                            let html = `
                                <table class="table table-bordered">
                                    <tr><th>Fiscal ID</th><td>${data.fiscalId || ''}</td></tr>
                                    <tr><th>Business Name</th><td>${data.businessName || ''}</td></tr>
                                    <tr><th>Email</th><td>${data.email || ''}</td></tr>
                                    <tr><th>Enabled</th><td>${data.enabled ? 'Yes' : 'No'}</td></tr>
                                    <tr><th>Email Alerts</th><td>${data.emailAlerts ? 'Yes' : 'No'}</td></tr>
                                    <tr><th>Locale</th><td>${data.locale || ''}</td></tr>
                                    <tr><th>Country</th><td>${data.country || ''}</td></tr>
                                    <tr><th>Sub Account ID</th><td>${data.subAccountId || 'N/A'}</td></tr>
                                </table>
                            `;
                            frappe.msgprint({
                                title: __('Business Registry Information'),
                                message: html,
                                indicator: 'blue'
                            });

                            // Aggiorna il flag se il Business Registry esiste
                            if (!frm.doc.business_registry_created) {
                                frm.set_value('business_registry_created', 1);
                                frm.save();
                            }
                        }
                    }
                });
            });
        }
    }
});
