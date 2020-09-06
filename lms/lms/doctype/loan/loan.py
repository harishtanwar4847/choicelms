# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import lms
from frappe.model.document import Document
from datetime import datetime

class Loan(Document):
	def get_customer(self):
		return frappe.get_doc('Customer', self.customer)

	def get_transaction_summary(self):
		# sauce: https://stackoverflow.com/a/23827026/9403680
		sql = """
			SELECT loan
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN transaction_amount END,0)) total_debits
				, SUM(COALESCE(CASE WHEN record_type = 'CR' THEN transaction_amount END,0)) total_credits
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN transaction_amount END,0)) 
				- SUM(COALESCE(CASE WHEN record_type = 'CR' THEN transaction_amount END,0)) outstanding 
			FROM `tabLoan Transaction`
			WHERE loan = '{}' 
			GROUP BY loan
			HAVING outstanding <> 0;
		""".format(self.name)

		res = frappe.db.sql(sql, as_dict=1)

		return res[0] if len(res) else frappe._dict({'loan': self.name, 'total_debits': 0, 'total_credits': 0, 'outstanding': 0})

	def check_for_shortfall(self):
		loan_margin_shortfall = frappe.get_doc({
			'doctype': 'Loan Margin Shortfall',
			'loan': self.name
		})

		loan_margin_shortfall.fill_items()

		if loan_margin_shortfall.margin_shortfall_action:
			loan_margin_shortfall.insert(ignore_permissions=True)

	def on_update(self):
		self.check_for_shortfall()
			

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