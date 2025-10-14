// Copyright (c) 2025, Solede and contributors
// For license information, please see license.txt

frappe.require('/assets/solede_openbanking/js/openbanking_helpers.js', function() {
    // Helper loaded
});

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
            // Bottone primario per importare transazioni (nero)
            if (frm.doc.business_registry_created) {
                frm.add_custom_button(__("Import Transactions"), () => {
                    // Mostra dialog per selezionare periodo
                    const today = frappe.datetime.get_today();
                    const last_month = frappe.datetime.add_months(today, -1);

                    frappe.prompt([
                        {
                            fieldname: 'from_date',
                            fieldtype: 'Date',
                            label: __('From Date'),
                            default: last_month,
                            reqd: 1
                        },
                        {
                            fieldname: 'to_date',
                            fieldtype: 'Date',
                            label: __('To Date'),
                            default: today,
                            reqd: 1
                        }
                    ], (values) => {
                        frappe.call({
                            method: "solede_openbanking.api.business_registry.import_transactions",
                            args: {
                                company: frm.doc.company,
                                from_date: values.from_date,
                                to_date: values.to_date
                            },
                            freeze: true,
                            freeze_message: __("Importing transactions..."),
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frappe.msgprint({
                                        title: __('Import Completed'),
                                        message: r.message.message,
                                        indicator: 'green'
                                    });
                                }
                            }
                        });
                    }, __('Import Transactions'), __('Import'));
                }).addClass('btn-primary');
            }

            // Menu dropdown "Actions" con tutte le altre azioni
            frm.add_custom_button(__("Generate Token"), () => {
                OpenBankingHelpers.call_api(
                    "solede_openbanking.api.authentication.generate_token",
                    { company: frm.doc.company },
                    "Generating authentication token...",
                    (r) => frm.reload_doc(),
                    "Token generated successfully"
                );
            }, __("Actions"));

            // Bottone per creare Business Registry (solo se non ancora creato)
            if (!frm.doc.business_registry_created) {
                frm.add_custom_button(__("Create Business Registry"), () => {
                    frappe.confirm(
                        __('Creating a Business Registry will incur a fee. Do you want to continue?'),
                        () => {
                            OpenBankingHelpers.call_api(
                                "solede_openbanking.api.business_registry.create_business_registry",
                                { company: frm.doc.company, password: "" },
                                "Creating Business Registry...",
                                (r) => frm.reload_doc(),
                                "Business Registry created successfully"
                            );
                        }
                    );
                }, __("Actions"));
            }

            if (frm.doc.business_registry_created) {
                // Bottone per avviare la connessione bancaria
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
                }, __("Actions"));

                // Bottone per recuperare gli account autorizzati
                frm.add_custom_button(__("Refresh Accounts"), () => {
                    OpenBankingHelpers.call_api(
                        "solede_openbanking.api.business_registry.get_accounts",
                        { company: frm.doc.company },
                        "Retrieving accounts...",
                        (r) => frm.reload_doc()
                    );
                }, __("Actions"));

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
                }, __("Actions"));
            }

            // Aggiungi bottoni per gestire gli account selezionati nella grid
            if (frm.doc.accounts && frm.doc.accounts.length > 0) {
                // Bottone Enable per account selezionati
                frm.fields_dict.accounts.grid.add_custom_button(__('Enable Selected'), function() {
                    OpenBankingHelpers.enable_selected_accounts(frm);
                });

                // Bottone Disable per account selezionati
                frm.fields_dict.accounts.grid.add_custom_button(__('Disable Selected'), function() {
                    OpenBankingHelpers.disable_selected_accounts(frm);
                });

                // Bottone Delete per account selezionati (solo se disabilitati)
                frm.fields_dict.accounts.grid.add_custom_button(__('Delete Selected'), function() {
                    OpenBankingHelpers.delete_selected_accounts(frm);
                });
            }
        }
    }
});
