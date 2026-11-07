# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt

import csv

from .base import BankCSVParser, movement


class RevolutBusinessParser(BankCSVParser):
	format_label = "Revolut Business"

	REQUIRED_COLUMNS = {
		"Date completed (UTC)",
		"ID",
		"Type",
		"State",
		"Description",
		"Reference",
		"Payer",
		"Payment currency",
		"Total amount",
		"Fee",
	}

	def parse(self, file_path):
		with open(file_path, newline="", encoding="utf-8-sig") as f:
			reader = csv.DictReader(f)
			missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or [])
			if missing:
				raise ValueError(
					f"File CSV Revolut Business non valido. Colonne mancanti: {sorted(missing)}"
				)

			lines = []
			for row in reader:
				if row["State"].strip() != "COMPLETED":
					continue

				total = _to_float(row["Total amount"])
				fee = _to_float(row["Fee"])
				payment_currency = row["Payment currency"].strip()
				orig_currency = (row.get("Orig currency") or "").strip() or None
				orig_amount = _to_float(row.get("Orig amount") or "0")

				# Se la valuta originale coincide con quella di pagamento, NON
				# e' un card payment multi-currency: lasciamo orig_* vuoti per
				# non confondere la logica di matching.
				if orig_currency and orig_currency == payment_currency:
					orig_currency = None
					orig_amount = 0.0

				beneficiary_iban = (
					(row.get("Beneficiary IBAN") or "").strip()
					or (row.get("Beneficiary account number") or "").strip()
					or None
				)

				lines.append(
					{
						"date": row["Date completed (UTC)"][:10],
						"transaction_id": row["ID"].strip(),
						"description": _build_description(row),
						**movement(total, fee),
						"currency": payment_currency,
						"transaction_type": row["Type"].strip(),
						"payer": row["Payer"].strip() or None,
						"solede_orig_currency": orig_currency,
						"solede_orig_amount": abs(orig_amount) if orig_currency else 0.0,
						"solede_beneficiary_iban": beneficiary_iban,
					}
				)
			return lines


def _to_float(value):
	value = value.strip()
	return float(value) if value else 0.0


def build_revolut_description(description: str, reference: str, tx_type: str) -> str:
	"""Compone la descrizione di una transazione Revolut nel formato 'desc - ref - [type]'.

	Usata sia dal parser CSV che dal client API REST per garantire che la stessa
	transazione, importata dalle due strade, abbia la stessa description (idempotenza).
	"""
	parts = []
	desc = (description or "").strip()
	if desc:
		parts.append(desc)
	ref = (reference or "").strip()
	if ref:
		parts.append(ref)
	tt = (tx_type or "").strip()
	if tt:
		parts.append(f"[{tt}]")
	return " - ".join(parts)


def _build_description(row):
	return build_revolut_description(row["Description"], row["Reference"], row["Type"])
