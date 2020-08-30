# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class LoanMarginShortfall(Document):
	def before_save(self):
		self.fill_items()

	def fill_items(self):
		loan = frappe.get_doc('Loan', self.loan)

		self.total_collateral_value = loan.total_collateral_value
		self.allowable_ltv = loan.allowable_ltv
		self.overdraft_limit = loan.overdraft_limit

		self.outstanding = loan.get_transaction_summary().outstanding
		self.ltv = (self.outstanding/self.total_collateral_value) * 100
		self.surplus_margin = 100 - self.ltv
		self.minimum_collateral_value = (100/self.allowable_ltv) * self.outstanding 

		# these give negative values
		# self.shortfall = (self.total_collateral_value - self.minimum_collateral_value) if self.outstanding > self.overdraft_limit else 0
		# self.shortfall_c = ((self.overdraft_limit - self.outstanding)*2) if self.outstanding > self.overdraft_limit else 0
		# self.shortfall_percentage = (self.overdraft_limit - self.outstanding) / 100

		self.shortfall = (self.minimum_collateral_value - self.total_collateral_value) if self.outstanding > self.overdraft_limit else 0
		self.shortfall_c = ((self.outstanding - self.overdraft_limit)*2) if self.outstanding > self.overdraft_limit else 0
		self.shortfall_percentage = (self.outstanding - self.overdraft_limit) / 100