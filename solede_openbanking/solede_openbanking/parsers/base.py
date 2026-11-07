# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt


def movement(total: float, fee: float = 0.0) -> dict:
	"""deposit / withdrawal / included_fee dal movimento totale firmato sul conto.

	`total` comprende già la commissione (semantica ERPNext `included_fee`, come il
	«Total amount» del CSV Revolut); `fee` è la quota di commissione dentro `total`.
	"""
	return {"deposit": max(total, 0.0), "withdrawal": max(-total, 0.0), "included_fee": abs(fee)}


class BankCSVParser:
	"""Base class for CSV bank statement parsers.

	Subclasses must override ``format_label`` and implement ``parse()`` to return
	a list of dicts with the following keys:

	- date (str, YYYY-MM-DD)
	- transaction_id (str, univoco — chiave di idempotenza)
	- description (str)
	- deposit (float, >= 0)
	- withdrawal (float, >= 0)
	- included_fee (float, >= 0)
	- currency (str)
	- transaction_type (str)
	- payer (str | None)
	"""

	format_label: str = ""

	def parse(self, file_path: str) -> list[dict]:
		raise NotImplementedError
