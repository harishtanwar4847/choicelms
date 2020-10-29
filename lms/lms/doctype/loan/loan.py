# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import lms
from frappe.model.document import Document
from datetime import datetime

class Loan(Document):
	def get_lender(self):
		return frappe.get_doc('Lender', self.lender)
	
	def after_insert(self):
		lender = self.get_lender()

		# Processing fees
		amount = lender.lender_processing_fees
		if lender.lender_processing_fees_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		loan_transaction = self.create_loan_transaction('Processing Fees', 'DR', amount)
		
		lender_sharing_amount = lender.lender_processing_fees_sharing
		if lender.lender_processing_fees_sharing_type == 'Percentage':
			lender_sharing_amount = (lender_sharing_amount/100) * amount
		spark_sharing_amount = amount - lender_sharing_amount
		self.create_lender_ledger(loan_transaction.name, amount, lender_sharing_amount, spark_sharing_amount)

		# Stamp Duty
		amount = lender.stamp_duty
		if lender.stamp_duty_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		loan_transaction = self.create_loan_transaction('Stamp Duty', 'DR', amount)

		lender_sharing_amount = lender.stamp_duty_sharing
		if lender.stamp_duty_sharing_type == 'Percentage':
			lender_sharing_amount = (lender_sharing_amount/100) * amount
		spark_sharing_amount = amount - lender_sharing_amount
		self.create_lender_ledger(loan_transaction.name, amount, lender_sharing_amount, spark_sharing_amount)

		# Documentation Charges
		amount = lender.documentation_charges
		if lender.documentation_charge_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		self.create_loan_transaction('Documentation Charges', 'DR', amount)

		lender_sharing_amount = lender.documentation_charges_sharing
		if lender.documentation_charge_sharing_type == 'Percentage':
			lender_sharing_amount = (lender_sharing_amount/100) * amount
		spark_sharing_amount = amount - lender_sharing_amount
		self.create_lender_ledger(loan_transaction.name, amount, lender_sharing_amount, spark_sharing_amount)

		# Mortgage Charges
		amount = lender.mortgage_charges
		if lender.mortgage_charge_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		self.create_loan_transaction('Mortgage Charges', 'DR', amount)

		lender_sharing_amount = lender.mortgage_charges_sharing
		if lender.mortgage_charge_sharing_type == 'Percentage':
			lender_sharing_amount = (lender_sharing_amount/100) * amount
		spark_sharing_amount = amount - lender_sharing_amount
		self.create_lender_ledger(loan_transaction.name, amount, lender_sharing_amount, spark_sharing_amount)

	def create_loan_transaction(self, transaction_type, record_type, amount):
		return frappe.get_doc({
			'doctype': 'Loan Transaction',
			'loan': self.name,
			'lender': self.lender,
			'amount': amount,
			'transaction_type': transaction_type,
			'record_type': record_type,
			'time': datetime.now()
		}).insert(ignore_permissions=True)

	def create_lender_ledger(self, loan_transaction_name, amount, lender_share, spark_share):
		frappe.get_doc({
			'doctype': 'Lender Ledger',
			'loan': self.name,
			'loan_transaction': loan_transaction_name,
			'lender': self.lender,
			'amount': amount,
			'lender_share': lender_share,
			'spark_share': spark_share,
		}).insert(ignore_permissions=True)

	def get_customer(self):
		return frappe.get_doc('Customer', self.customer)

	def get_transaction_summary(self):
		# sauce: https://stackoverflow.com/a/23827026/9403680
		sql = """
			SELECT loan
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN amount END,0)) total_debits
				, SUM(COALESCE(CASE WHEN record_type = 'CR' THEN amount END,0)) total_credits
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN amount END,0)) 
				- SUM(COALESCE(CASE WHEN record_type = 'CR' THEN amount END,0)) outstanding 
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

			loan_margin_shortfall = self.get_margin_shortfall()

			loan_margin_shortfall.fill_items()

			if loan_margin_shortfall.margin_shortfall_action:
				loan_margin_shortfall.insert(ignore_permissions=True)

	def get_margin_shortfall(self):
		margin_shortfall_name = frappe.db.get_value('Loan Margin Shortfall', {'loan': self.name, 'status': 'Pending'}, 'name')
		if not margin_shortfall_name:
			margin_shortfall = frappe.new_doc('Loan Margin Shortfall')
			margin_shortfall.loan = self.name
			return margin_shortfall

		return frappe.get_doc('Loan Margin Shortfall', margin_shortfall_name)

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

def get_permission_query_conditions(user):
	if not user: user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None
	elif "Lender" in frappe.get_roles(user):
		roles = frappe.get_roles(user)

		return """(`tabLoan`.lender in {role_tuple})"""\
			.format(role_tuple=lms.convert_list_to_tuple_string(roles))