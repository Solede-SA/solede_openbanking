# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt

from .corner_bank import CornerBankParser
from .revolut_business import RevolutBusinessParser

PARSERS = {
	RevolutBusinessParser.format_label: RevolutBusinessParser,
	CornerBankParser.format_label: CornerBankParser,
}


def get_parser(format_name):
	if format_name not in PARSERS:
		raise ValueError(
			f"Formato CSV non supportato: {format_name}. Disponibili: {sorted(PARSERS)}"
		)
	return PARSERS[format_name]()
