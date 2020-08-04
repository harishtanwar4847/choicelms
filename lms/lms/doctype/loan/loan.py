# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import lms
from frappe.model.document import Document
from datetime import datetime

class Loan(Document):
	def check_for_shortfall(self):
		new_prices = lms.get_security_prices([item.get('isin') for item in self.items])
		new_total = 0
		for item in self.items:
			item.new_price = new_prices.get(item.get('isin'))
			item.new_amount = item.get('pledged_quantity') * item.get('new_price')
			new_total += item.get('new_amount')

		self.new_total = new_total
		self.time = datetime.now()
		self.shortfall_percentage = 0
		self.is_shortfall = 0
		percentage_of_original_total = (self.new_total / self.total) * 100
		
		if percentage_of_original_total < 100:
			self.shortfall_percentage = 100 - percentage_of_original_total
			self.is_shortfall = 1
		
		self.save(ignore_permissions=True)
		frappe.db.commit()
			

def check_loans_for_shortfall(loans):
	for loan_name in loans:
		frappe.enqueue_doc('Loan', loan_name, method='check_for_shortfall')

@frappe.whitelist()
def check_all_loans_for_shortfall():
	chunks = lms.chunk_doctype(doctype='Loan', limit=50)

	for start in chunks.get('chunks'):
		loan_list = frappe.db.get_all('Loan', limit_page_length=chunks.get('limit'), limit_start=start)

		frappe.enqueue(
			method='lms.lms.doctype.loan.loan.check_loans_for_shortfall', 
			loans=[i.name for i in loan_list],
			queue='long'
		)