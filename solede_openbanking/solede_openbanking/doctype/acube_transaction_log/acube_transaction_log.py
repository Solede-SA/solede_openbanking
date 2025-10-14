# Copyright (c) 2025, Solede and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ACubeTransactionLog(Document):
	def before_insert(self):
		"""Set sync date before inserting"""
		if not self.sync_date:
			self.sync_date = frappe.utils.now()
