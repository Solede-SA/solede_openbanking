# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt

import csv
import re

from .base import BankCSVParser, movement

_OUR_REF_RE = re.compile(r"Our ref:\s*(\S+)")
_ACCOUNT_CURRENCY_RE = re.compile(r"\d+/\d+\s+([A-Z]{3})")

_PAYER_SKIP_PREFIXES = (
	"Your order", "When reclaiming", "01-145", "Fees", "Expenses", "Charged at",
	"CH -", "CH-", "LT -", "KUNDENNUMMER", "RECHNUNGSNUMMER", "RECHNUNGSDATUM",
	"FATTURA", "ID:", "EBB", "LEASINGVERTRAG", "PRORATA", "CANONE", "LEASING",
	"Order amount", "Our ref",
)

_FEE_DESCRIPTIONS = {"Accounting summary", "Payment service statement"}


class CornerBankParser(BankCSVParser):
	"""Parser CSV Corner Banca (export ListaDettagliMovimenti).

	Separatore `;`. Ogni transazione occupa più righe: la prima ha `Account No.` popolato,
	le successive hanno solo `Description`/`Detail` con controparte, IBAN, `Our ref: ...`.
	`Our ref` è la chiave di idempotenza.
	"""

	format_label = "Corner Bank"

	def parse(self, file_path):
		with open(file_path, newline="", encoding="utf-8-sig") as f:
			rows = list(csv.reader(f, delimiter=";"))

		self._currency = _detect_currency(rows)

		header_idx = None
		for i, row in enumerate(rows):
			if len(row) >= 7 and row[1] == "Account No." and row[2] == "Registration date":
				header_idx = i
				break
		if header_idx is None:
			raise ValueError("Intestazione Corner Bank non trovata (riga 'Account No.;Registration date;...')")

		transactions = []
		current = None
		for row in rows[header_idx + 1:]:
			if len(row) < 7:
				continue
			account_no = row[1].strip()
			if account_no:
				if current:
					transactions.append(current)
				current = {
					"registration_date": row[2].strip(),
					"description": row[3].strip(),
					"amount_raw": row[6].strip(),
					"detail_lines": [],
				}
			elif current is not None:
				detail = " ".join(p for p in (row[3].strip(), row[4].strip()) if p)
				if detail:
					current["detail_lines"].append(detail)
		if current:
			transactions.append(current)

		return [self._build_line(t) for t in transactions if t["amount_raw"]]

	def _build_line(self, tx):
		amount = float(tx["amount_raw"])
		our_ref = _find_our_ref(tx["detail_lines"])
		if not our_ref:
			raise ValueError(f"Transazione Corner senza 'Our ref': {tx}")

		payer = _extract_payer(tx["detail_lines"])
		return {
			"date": _parse_date(tx["registration_date"]),
			"transaction_id": our_ref,
			"description": _build_description(tx["description"], payer, tx["detail_lines"]),
			**movement(amount),
			"currency": self._currency,
			"transaction_type": _map_transaction_type(tx["description"]),
			"payer": payer,
		}


def _detect_currency(rows):
	for row in rows[:15]:
		for cell in row:
			m = _ACCOUNT_CURRENCY_RE.search(cell or "")
			if m:
				return m.group(1)
	raise ValueError("Currency non rilevata nell'intestazione Corner Bank (es. '272963/01 CHF')")


def _parse_date(s):
	d, m, y = s.split("/")
	return f"20{y}-{m.zfill(2)}-{d.zfill(2)}"


def _find_our_ref(details):
	for line in details:
		m = _OUR_REF_RE.search(line)
		if m:
			return m.group(1)
	return None


def _extract_payer(details):
	for line in details:
		if any(line.startswith(p) for p in _PAYER_SKIP_PREFIXES):
			continue
		if re.match(r"^=?\"?\d{6,}", line) or re.match(r"^CH\d{2}", line):
			continue
		if line.isupper() and 3 <= len(line) <= 60:
			return line
		if line.startswith("AVV."):
			return line
	return None


def _build_description(base_desc, payer, details):
	parts = [base_desc]
	if payer:
		parts.append(payer)
	for line in details:
		if line.startswith("FATTURA") or line.startswith("RECHNUNGSNUMMER"):
			parts.append(line)
			break
	return " - ".join(p for p in parts if p)


def _map_transaction_type(description):
	if description in _FEE_DESCRIPTIONS:
		return "FEE"
	return description.upper().replace(" ", "_")
