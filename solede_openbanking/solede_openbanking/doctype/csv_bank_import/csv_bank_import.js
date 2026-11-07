// Copyright (c) 2026, Solede SA and contributors
// For license information, please see license.txt

frappe.ui.form.on("CSV Bank Import", {
	refresh(frm) {
		if (frm.doc.status === "Draft" && frm.doc.csv_file && frm.doc.format && frm.doc.bank_account) {
			frm.add_custom_button(__("1. Parsa File"), function () {
				frm.call({
					method: "parse_file",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Parsing CSV..."),
					callback: () => frm.reload_doc(),
				});
			}, __("Azioni"));
		}

		if (frm.doc.status === "Parsed") {
			frm.add_custom_button(__("2. Crea Bank Transactions"), function () {
				frappe.confirm(
					__("Creare le Bank Transaction per tutte le righe Pending?"),
					function () {
						frm.call({
							method: "create_bank_transactions",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("Creazione Bank Transactions..."),
							callback: () => frm.reload_doc(),
						});
					}
				);
			}, __("Azioni")).addClass("btn-primary");
		}

		if (frm.doc.status !== "Draft") {
			frm.dashboard.add_indicator(
				__("Totali: {0}", [frm.doc.total_transactions || 0]),
				"blue"
			);
			if (frm.doc.created_count) {
				frm.dashboard.add_indicator(
					__("Create: {0}", [frm.doc.created_count]),
					"green"
				);
			}
			if (frm.doc.skipped_count) {
				frm.dashboard.add_indicator(
					__("Saltate: {0}", [frm.doc.skipped_count]),
					"orange"
				);
			}
		}
	},

	csv_file(frm) {
		if (frm.doc.status !== "Draft") {
			frm.set_value("status", "Draft");
			frm.set_value("transactions", []);
			frm.set_value("total_transactions", 0);
			frm.set_value("total_credit", 0);
			frm.set_value("total_debit", 0);
			frm.set_value("created_count", 0);
			frm.set_value("skipped_count", 0);
		}
	},
});
