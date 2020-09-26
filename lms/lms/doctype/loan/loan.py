# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import lms
from frappe.model.document import Document
from datetime import datetime

class Loan(Document):
	def after_insert(self):
		# fetch lender details
		lender_doc = frappe.get_doc("Lender", "LENDER000001").as_dict()
		
		# variable defined for fixed loan transactions
		purposes = [
			{
				"type_field":"lender_processing_fees_type",
				"value_field":"lender_processing_fees",
				"label":'Lender Processing Fees'
			},
			{
				"type_field":"stamp_duty_type",
				"value_field":"stamp_duty",
				"label":'Stamp Duty'
			},
			{
				"type_field":"documentation_charge_type",
				"value_field":"documentation_charges",
				"label":'Documentation Charges'
			},
			{
				"type_field":"mortgage_charge_type",
				"value_field":"mortgage_charges",
				"label":'Mortgage Charges'
			},
		]

		for purpose in purposes:
			# create loan transaction
			transaction_amt = lender_doc[purpose['value_field']]
			if lender_doc[purpose["type_field"]] == "Percentage":
				transaction_amt = (self.total_collateral_value*lender_doc[purpose['value_field']])/100
			
			loan_transaction = frappe.get_doc({
				'doctype': 'Loan Transaction',
				"loan":self.name,
				"transaction_amount":transaction_amt,
				"purpose":purpose['label'],
				"record_type":"DR",
				"transaction_time":datetime.now()
			})

			loan_transaction.insert(ignore_permissions=True)

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

	def fill_items(self):
		self.total_collateral_value = 0
		for i in self.items:
			i.amount = i.price * i.pledged_quantity
			self.total_collateral_value += i.amount

		self.overdraft_limit = (self.allowable_ltv/100) * self.total_collateral_value

	def check_for_shortfall(self):
		check = False

		securities_price_map = lms.get_security_prices([i.isin for i in self.items])

		for i in self.items:
			if i.price != securities_price_map.get(i.isin):
				check = True
				i.price = securities_price_map.get(i.isin)

		if check:
			lms.loan_timeline(self.name)
			self.fill_items()
			self.save(ignore_permissions=True)

			loan_margin_shortfall = frappe.get_doc({
				'doctype': 'Loan Margin Shortfall',
				'loan': self.name
			})

			loan_margin_shortfall.fill_items()

			if loan_margin_shortfall.margin_shortfall_action:
				loan_margin_shortfall.insert(ignore_permissions=True)

	def get_updated_total_collateral_value(self):
		securities = [i.isin for i in self.items]

		securities_price_map = lms.get_security_prices(securities)

		updated_total_collateral_value = 0

		for i in self.items:
			updated_total_collateral_value += i.pledged_quantity * securities_price_map.get(i.isin)

		return updated_total_collateral_value
			

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