# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class LoanTransaction(Document):
	def after_insert(self):
		frappe.enqueue_doc('Loan', self.loan, method='check_for_shortfall')
