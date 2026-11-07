// Copyright (c) 2026, Solede SA and contributors
// For license information, please see license.txt

// Status strings allineati al Select del doctype Revolut Connection.
// Niente costanti modulo per evitare TDZ con il bundler esbuild di Frappe.

frappe.ui.form.on("Revolut Connection", {
	refresh(frm) {
		_render_status_banner(frm);
		_render_connect_button(frm);
		_render_sync_button(frm);
		_render_backfill_button(frm);
		_render_accounts_tab(frm);
	},
});

function _render_status_banner(frm) {
	if (frm.is_new()) return;
	if (frm.doc.connection_status === "Needs Reauth") {
		const err = frappe.utils.escape_html(frm.doc.last_auth_error || "");
		frm.dashboard.set_headline_alert(
			__("⚠️ Connessione disattivata: refresh_token revocato.") +
				` <code>${err}</code> ` +
				__("Premi 'Riconnetti' per riattivare."),
			"red"
		);
	} else if (frm.doc.connection_status === "Connected") {
		const last = frm.doc.last_sync_at
			? frappe.datetime.str_to_user(frm.doc.last_sync_at)
			: __("mai");
		frm.dashboard.set_headline_alert(
			__("✅ Connessione attiva. Ultimo sync: {0}", [last]),
			"green"
		);
	}
}

function _render_connect_button(frm) {
	if (frm.is_new()) return;

	let label;
	if (frm.doc.connection_status === "Connected") {
		label = __("Riautorizza");
	} else if (frm.doc.connection_status === "Needs Reauth") {
		label = __("Riconnetti");
	} else {
		label = __("Connetti a Revolut");
	}

	frm.add_custom_button(label, () => {
		frappe.call({
			method: "solede_openbanking.api.revolut.start_oauth_flow",
			args: { connection: frm.doc.name },
			freeze: true,
			freeze_message: __("Apertura consent screen Revolut…"),
			callback(r) {
				if (r.message && r.message.consent_url) {
					window.open(r.message.consent_url, "_blank", "noopener");
					frappe.show_alert({
						message: __(
							"Completa l'autorizzazione nella nuova finestra. Al ritorno, il record si aggiornerà a Connected."
						),
						indicator: "blue",
					});
				}
			},
		});
	});
}

function _render_accounts_tab(frm) {
	const $wrapper = frm.fields_dict.accounts_html?.$wrapper;
	if (!$wrapper) return;

	if (frm.is_new()) {
		$wrapper.html(
			`<div class="text-muted" style="padding:20px">${__(
				"Salva la connessione e completa il consent OAuth per visualizzare gli account."
			)}</div>`
		);
		return;
	}

	if (frm.doc.connection_status !== "Connected") {
		$wrapper.html(
			`<div class="text-muted" style="padding:20px">${__(
				"Connessione non attiva ({0}). Completa il consent OAuth per visualizzare gli account.",
				[frm.doc.connection_status || "—"]
			)}</div>`
		);
		return;
	}

	$wrapper.html(
		`<div class="text-muted" style="padding:20px">${__(
			"Caricamento account Revolut…"
		)}</div>`
	);

	frappe.call({
		method: "solede_openbanking.api.revolut.list_accounts",
		args: { connection: frm.doc.name },
		callback(r) {
			const accounts = r.message || [];
			if (!accounts.length) {
				$wrapper.html(
					`<div class="text-muted" style="padding:20px">${__(
						"Nessun account restituito da Revolut."
					)}</div>`
				);
				return;
			}
			_paint_accounts_table(frm, $wrapper, accounts);
		},
		error() {
			$wrapper.html(
				`<div class="text-danger" style="padding:20px">${__(
					"Errore nel recupero degli account. Vedi Error Log."
				)}</div>`
			);
		},
	});
}

function _paint_accounts_table(frm, $wrapper, accounts) {
	const rows = accounts
		.map((a) => {
			const mapped = a.mapped_to
				? `<span style="color:#2c7a2c">✓ <a href="/app/bank-account/${encodeURIComponent(
						a.mapped_to.bank_account
					)}">${frappe.utils.escape_html(
						a.mapped_to.bank_account
					)}</a></span>`
				: '<span style="color:#aa6600">—</span>';
			const action_btn = a.mapped_to
				? `<button class="btn btn-xs btn-default revolut-unmap-btn" data-uuid="${a.uuid}" data-bank-account="${frappe.utils.escape_html(
						a.mapped_to.bank_account
					)}">${__("Rimuovi mappatura")}</button>`
				: `<button class="btn btn-xs btn-primary revolut-map-btn" data-uuid="${a.uuid}" data-currency="${a.currency}" data-name="${frappe.utils.escape_html(
						a.name || ""
					)}">${__("Mappa…")}</button>`;
			return `
				<tr>
					<td>${frappe.utils.escape_html(a.name || "")}</td>
					<td>${frappe.utils.escape_html(a.currency || "")}</td>
					<td class="num">${frappe.format(a.balance, { fieldtype: "Float", precision: 2 })}</td>
					<td>${frappe.utils.escape_html(a.state || "")}</td>
					<td><code style="font-size:10px">${frappe.utils.escape_html(a.uuid || "")}</code></td>
					<td>${mapped}</td>
					<td>${action_btn}</td>
				</tr>`;
		})
		.join("");

	const html = `
		<style>
			.revolut-accounts-wrapper { padding: 0; }
			.revolut-accounts-toolbar {
				display: flex; justify-content: space-between; align-items: center;
				margin-bottom: 10px; padding: 0 5px;
			}
			.revolut-accounts-toolbar small { color: #888; }
			.revolut-accounts-table {
				width: 100%; border-collapse: collapse; font-size: 12px;
				background: var(--card-bg, #fff);
			}
			.revolut-accounts-table th, .revolut-accounts-table td {
				border: 1px solid var(--border-color, #eee);
				padding: 8px 10px; text-align: left; vertical-align: middle;
			}
			.revolut-accounts-table th {
				background: var(--bg-light-gray, #f5f5f5);
				font-weight: 600;
			}
			.revolut-accounts-table .num {
				text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap;
			}
			.revolut-accounts-table tr:hover td { background: var(--bg-light-gray, #fafafa); }
		</style>
		<div class="revolut-accounts-wrapper">
			<div class="revolut-accounts-toolbar">
				<small>${__(
					"Lista in tempo reale degli account Revolut. Mappa ogni account a un Bank Account ERPNext per attivarne il sync."
				)}</small>
				<button class="btn btn-xs btn-default revolut-refresh-btn">${__("Aggiorna")}</button>
			</div>
			<table class="revolut-accounts-table">
				<thead>
					<tr>
						<th>${__("Nome")}</th>
						<th>${__("Valuta")}</th>
						<th class="num">${__("Saldo")}</th>
						<th>${__("Stato")}</th>
						<th>UUID</th>
						<th>${__("Bank Account ERPNext")}</th>
						<th></th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>`;

	$wrapper.html(html);

	$wrapper.find(".revolut-refresh-btn").on("click", () => _render_accounts_tab(frm));

	$wrapper.find(".revolut-map-btn").on("click", function () {
		const uuid = $(this).data("uuid");
		const currency = $(this).data("currency");
		const name = $(this).data("name");
		_prompt_map_to_bank_account(frm, uuid, currency, name, () =>
			_render_accounts_tab(frm)
		);
	});

	$wrapper.find(".revolut-unmap-btn").on("click", function () {
		const uuid = $(this).data("uuid");
		const bank_account = $(this).data("bank-account");
		frappe.confirm(
			__(
				"Rimuovere la mappatura tra <code>{0}</code> e <strong>{1}</strong>?<br><br>Le Bank Transaction già importate restano. Il sync futuro ignorerà le transazioni di questo account.",
				[uuid, bank_account]
			),
			() => {
				frappe.call({
					method: "solede_openbanking.api.revolut.unmap_account",
					args: { bank_account },
					freeze: true,
					callback() {
						frappe.show_alert({
							message: __("Mappatura rimossa"),
							indicator: "orange",
						});
						_render_accounts_tab(frm);
					},
				});
			}
		);
	});
}

function _prompt_map_to_bank_account(frm, uuid, currency, account_name, on_done) {
	const map_dlg = new frappe.ui.Dialog({
		title: __("Mappa account Revolut a Bank Account"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div style="margin-bottom:10px">
					<strong>${__("Account Revolut")}:</strong> ${frappe.utils.escape_html(account_name)} (${currency})<br>
					<small><code>${uuid}</code></small>
				</div>`,
			},
			{
				fieldtype: "Link",
				fieldname: "bank_account",
				label: __("Bank Account ERPNext"),
				options: "Bank Account",
				reqd: 1,
				get_query: () => ({
					filters: { bank: frm.doc.bank, disabled: 0 },
				}),
				description: __(
					"Bank Account legato al Bank '{0}'. Crea un nuovo Bank Account se non ne hai uno per questa valuta.",
					[frm.doc.bank]
				),
			},
		],
		primary_action_label: __("Mappa"),
		primary_action(values) {
			frappe.call({
				method: "solede_openbanking.api.revolut.map_account_to_bank_account",
				args: {
					connection: frm.doc.name,
					revolut_account_uuid: uuid,
					bank_account: values.bank_account,
				},
				freeze: true,
				callback(r) {
					if (r.message) {
						frappe.show_alert({
							message: __("Mappato a {0}", [r.message]),
							indicator: "green",
						});
						map_dlg.hide();
						if (on_done) on_done();
					}
				},
			});
		},
	});
	map_dlg.show();
}

function _render_backfill_button(frm) {
	if (frm.is_new() || frm.doc.connection_status !== "Connected") return;

	frm.add_custom_button(
		__("Backfill da data…"),
		() => {
			const dlg = new frappe.ui.Dialog({
				title: __("Backfill storico Revolut"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<div class="text-muted" style="margin-bottom:10px">${__(
							"Ri-scarica le transazioni dalla data scelta a oggi. Non modifica il cursore del sync giornaliero ed è idempotente (inserisce solo le transazioni mancanti). Utile dopo aver mappato un nuovo conto, per recuperare lo storico."
						)}</div>`,
					},
					{
						fieldtype: "Date",
						fieldname: "from_date",
						label: __("Da data"),
						default: frm.doc.cutover_date,
						reqd: 1,
					},
				],
				primary_action_label: __("Avvia backfill"),
				primary_action(values) {
					frappe.call({
						method: "solede_openbanking.revolut_sync.backfill_connection",
						args: { connection_name: frm.doc.name, from_date: values.from_date },
						freeze: true,
						freeze_message: __("Backfill in corso… può richiedere un po' di tempo."),
						callback(r) {
							if (!r.message) return;
							const m = r.message;
							dlg.hide();
							_show_pull_result(__("Backfill completato"), m);
							frm.reload_doc();
						},
					});
				},
			});
			dlg.show();
		},
		__("Azioni")
	);
}

function _render_sync_button(frm) {
	if (frm.is_new() || frm.doc.connection_status !== "Connected") return;

	frm.add_custom_button(
		__("Sync Now"),
		() => {
			frappe.confirm(
				__(
					"Avvio il sync delle transazioni Revolut per <strong>{0}</strong>?",
					[frm.doc.bank]
				),
				() => {
					frappe.call({
						method: "solede_openbanking.revolut_sync.sync_now",
						args: { connection_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Sync in corso…"),
						callback(r) {
							if (r.message) {
								const m = r.message;
								_show_pull_result(__("Sync completato"), m);
								frm.reload_doc();
							}
						},
					});
				}
			);
		},
		__("Azioni")
	);
}

// Esito di sync/backfill. Le differenze sono righe già importate (es. da ACube o CSV)
// che non coincidono con Revolut: non vengono corrette in automatico.
function _show_pull_result(title, m) {
	const esc = (v) => frappe.utils.escape_html(String(v ?? ""));
	const labels = {
		date: __("Data"),
		deposit: __("Entrata"),
		withdrawal: __("Uscita"),
		included_fee: __("Commissione"),
	};
	const rows = m.mismatches
		.flatMap(({ bank_transaction, differences }) =>
			Object.entries(differences).map(
				([field, [ours, theirs]]) =>
					`<tr><td><a href="/app/bank-transaction/${encodeURIComponent(bank_transaction)}">${esc(
						bank_transaction
					)}</a></td><td>${labels[field]}</td><td>${esc(ours)}</td><td>${esc(theirs)}</td></tr>`
			)
		)
		.join("");
	const intro = __("Righe già presenti che non coincidono con Revolut (non corrette):");
	const head = `<tr><th>Bank Transaction</th><th>${__("Campo")}</th><th>ERPNext</th><th>Revolut</th></tr>`;
	const table = rows
		? `<p style="margin-top:12px">${intro}</p>` +
			`<table class="table table-bordered table-sm"><thead>${head}</thead><tbody>${rows}</tbody></table>`
		: "";
	frappe.msgprint({
		title,
		indicator: rows ? "orange" : "green",
		wide: true,
		message:
			__("Create: {0} — Aggiornate: {1} — Saltate: {2} — Non mappate: {3}", [
				m.created,
				m.updated,
				m.skipped,
				m.unmapped,
			]) + table,
	});
}
