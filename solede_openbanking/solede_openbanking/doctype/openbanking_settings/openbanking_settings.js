// Copyright (c) 2025, Solede and contributors
// For license information, please see license.txt

frappe.ui.form.on("OpenBanking Settings", {
    refresh(frm) {
        if (!frm.is_new()) {
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

            // Gestione azioni sugli account nella child table
            frm.fields_dict['accounts'].grid.wrapper.on('click', '.grid-row', function(e) {
                const row = $(this);
                const row_index = row.index();
                const account = frm.doc.accounts[row_index];

                if (!account) return;

                // Aggiungi bottoni solo se non già presenti
                if (row.find('.account-actions').length === 0) {
                    const actions_html = `
                        <div class="account-actions" style="margin-top: 5px;">
                            ${account.enabled ?
                                '<button class="btn btn-xs btn-warning btn-disable-account">Disable</button>' :
                                '<button class="btn btn-xs btn-success btn-enable-account">Enable</button>'
                            }
                            <button class="btn btn-xs btn-danger btn-delete-account" ${account.enabled ? 'disabled' : ''}>Delete</button>
                        </div>
                    `;
                    row.find('[data-fieldname="enabled"]').closest('.form-group').append(actions_html);
                }
            });

            // Handler per Enable account
            $(document).on('click', '.btn-enable-account', function(e) {
                e.stopPropagation();
                const row = $(this).closest('.grid-row');
                const row_index = row.index();
                const account = frm.doc.accounts[row_index];

                frappe.call({
                    method: "solede_openbanking.api.business_registry.toggle_account",
                    args: {
                        company: frm.doc.company,
                        uuid: account.uuid,
                        enabled: 1
                    },
                    freeze: true,
                    freeze_message: __("Enabling account..."),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: r.message.message,
                                indicator: "green"
                            }, 3);
                            frm.reload_doc();
                        }
                    }
                });
            });

            // Handler per Disable account
            $(document).on('click', '.btn-disable-account', function(e) {
                e.stopPropagation();
                const row = $(this).closest('.grid-row');
                const row_index = row.index();
                const account = frm.doc.accounts[row_index];

                frappe.confirm(
                    __('Disabling this account will clear its balance, extra data, and transactions. Continue?'),
                    () => {
                        frappe.call({
                            method: "solede_openbanking.api.business_registry.toggle_account",
                            args: {
                                company: frm.doc.company,
                                uuid: account.uuid,
                                enabled: 0
                            },
                            freeze: true,
                            freeze_message: __("Disabling account..."),
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: "orange"
                                    }, 3);
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            });

            // Handler per Delete account
            $(document).on('click', '.btn-delete-account', function(e) {
                e.stopPropagation();
                const row = $(this).closest('.grid-row');
                const row_index = row.index();
                const account = frm.doc.accounts[row_index];

                frappe.confirm(
                    __('This will delete the account and all associated accounts from the same bank connection. All accounts must be disabled first. Continue?'),
                    () => {
                        frappe.call({
                            method: "solede_openbanking.api.business_registry.delete_account",
                            args: {
                                company: frm.doc.company,
                                uuid: account.uuid
                            },
                            freeze: true,
                            freeze_message: __("Deleting account..."),
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: "red"
                                    }, 3);
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            });

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
