# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import lms
from frappe.model.document import Document
from datetime import datetime, timedelta
from lms.lms.doctype.loan_transaction.loan_transaction import LoanTransaction

class Loan(Document):
	def get_lender(self):
		return frappe.get_doc('Lender', self.lender)
	
	def after_insert(self):
		lender = self.get_lender()

		# Processing fees
		amount = lender.lender_processing_fees
		if lender.lender_processing_fees_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		processing_fees_transaction_id = self.get_new_transaction_id()
		self.create_loan_transaction('Processing Fees', amount, approve=True, transaction_id=processing_fees_transaction_id)

		# Stamp Duty
		amount = lender.stamp_duty
		if lender.stamp_duty_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		stamp_duty_transaction_id = self.get_new_transaction_id()
		self.create_loan_transaction('Stamp Duty', amount, approve=True, transaction_id=stamp_duty_transaction_id)

		# Documentation Charges
		amount = lender.documentation_charges
		if lender.documentation_charge_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		documentation_charges_transaction_id = self.get_new_transaction_id()
		self.create_loan_transaction('Documentation Charges', amount, approve=True, transaction_id=documentation_charges_transaction_id)

		# Mortgage Charges
		amount = lender.mortgage_charges
		if lender.mortgage_charge_type == 'Percentage':
			amount = (amount/100) * self.sanctioned_limit
		mortgage_charges_transaction_id = self.get_new_transaction_id()
		self.create_loan_transaction('Mortgage Charges', amount, approve=True, transaction_id=mortgage_charges_transaction_id)

	def get_new_transaction_id(self):
		latest_transaction = frappe.db.sql("select transaction_id from `tabLoan Transaction` where loan='{}' and transaction_id like 'loan-%' order by creation desc limit 1".format(self.name), as_dict=True)
		if len(latest_transaction) == 0:
			return "{}-0001".format(self.name)

		latest_transaction_id = latest_transaction[0].transaction_id.split("-")[1]
		new_transaction_id =  "{}-".format(self.name) + ("%04d" % (int(latest_transaction_id) + 1))
		return new_transaction_id

	def create_loan_transaction(self, transaction_type, amount, approve=False, transaction_id=None):
		loan_transaction = frappe.get_doc({
			'doctype': 'Loan Transaction',
			'loan': self.name,
			'lender': self.lender,
			'amount': amount,
			'transaction_type': transaction_type,
			'record_type': LoanTransaction.loan_transaction_map.get(transaction_type, 'DR'),
			'time': datetime.now()
		})

		if transaction_id:
			loan_transaction.transaction_id = transaction_id
		
		loan_transaction.insert(ignore_permissions=True)

		if approve:
			loan_transaction.status = 'Approved'
			loan_transaction.workflow_state = 'Approved'
			loan_transaction.docstatus = 1
			loan_transaction.save(ignore_permissions=True)
		
		frappe.db.commit()
		return loan_transaction

	def get_customer(self):
		return frappe.get_doc('Customer', self.customer)

	def update_loan_balance(self):
		summary = self.get_transaction_summary()
		self.balance = summary.get('outstanding')
		self.save(ignore_permissions=True)
		frappe.db.commit()

	def on_update(self):
		frappe.enqueue_doc('Loan', self.name, method='check_for_shortfall')

	def get_transaction_summary(self):
		# sauce: https://stackoverflow.com/a/23827026/9403680
		sql = """
			SELECT loan
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN amount END,0)) total_debits
				, SUM(COALESCE(CASE WHEN record_type = 'CR' THEN amount END,0)) total_credits
				, SUM(COALESCE(CASE WHEN record_type = 'DR' THEN amount END,0)) 
				- SUM(COALESCE(CASE WHEN record_type = 'CR' THEN amount END,0)) outstanding 
			FROM `tabLoan Transaction`
			WHERE loan = '{}' AND docstatus = 1
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

		drawing_power = self.total_collateral_value * (self.allowable_ltv/100)
		self.drawing_power = drawing_power if drawing_power <= self.sanctioned_limit else self.sanctioned_limit

	def check_for_shortfall(self):
		check = False

		securities_price_map = lms.get_security_prices([i.isin for i in self.items])

		for i in self.items:
			if i.price != securities_price_map.get(i.isin):
				check = True
				i.price = securities_price_map.get(i.isin)

		if check:
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
	
	def get_base_interest_percentage(self):
		base_interest = frappe.db.get_value("Interest Configuration", {'lender':self.lender, 'from_amount':['<=',self.balance], 'to_amount':['>=',self.balance]}, ['base_interest'])
		return base_interest
	
	def add_virtual_interest(self, input_date=None):
		base_interest_percent = self.get_base_interest_percentage()
		if input_date:
			input_date = datetime.strptime(input_date, '%Y-%m-%d')
		else:
			input_date = datetime.now()

		# get no of days of month
		num_of_days_in_month = ((input_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)).day
		virtual_interest = base_interest_percent / num_of_days_in_month
		amount = self.balance * virtual_interest / 100
		virtual_interest_doc = frappe.get_doc({
			'doctype': 'Virtual Interest',
			'lender': self.lender,
			'loan': self.name,
			'time': input_date.replace(hour=23, minute=59, second=59, microsecond=999999),
			'amount': amount,
		})
		virtual_interest_doc.save(ignore_permissions=True)
		frappe.db.commit()
		return virtual_interest_doc

	def book_all_virtual_interest_for_month(self, input_date=None):
		if input_date:
			input_date = datetime.strptime(input_date, '%Y-%m-%d')
		else:
			input_date = datetime.now()
		
		month = input_date.strftime("%m")
		year = input_date.strftime("%Y")

		# book virtual interest for that month and year
		frappe.db.sql("update `tabVirtual Interest` set is_booked = 1 where loan = '{}' and is_booked = 0 and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(self.name, year, month))
		frappe.db.commit()

	def create_interest_transaction(self):
		current_date = datetime.now()
		month = current_date.strftime("%m")
		year = current_date.strftime("%Y")

		check_if_exist = frappe.db.sql("select count(name) as total_count from `tabLoan Transaction` where loan = '{}' and lender = '{}' and transaction_type = 'Interests' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(self.name, self.lender, year, month), as_dict=1)

		if check_if_exist[0]['total_count'] == 0:
			virtual_interest_sum = frappe.db.sql("select sum(amount) as amount from `tabVirtual Interest` where loan = '{}' and lender = '{}' and is_booked = 1 and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {}".format(self.name, self.lender, year, month), as_dict=1) 

			loan_transaction = frappe.get_doc({
				'doctype': 'Loan Transaction',
				'loan': self.name,
				'lender': self.lender,
				'amount': virtual_interest_sum[0]["amount"],
				'transaction_type': 'Interests',
				'record_type': 'DR',
				'time': datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
			})
			loan_transaction.insert(ignore_permissions=True)
			loan_transaction.transaction_id = loan_transaction.name
			loan_transaction.status = 'Approved'
			loan_transaction.workflow_state = 'Approved'
			loan_transaction.docstatus = 1
			loan_transaction.save(ignore_permissions=True)
			frappe.db.commit()

			return loan_transaction.as_dict()

	def get_rebate_threshold(self):
		rebate_threshold = frappe.db.get_value("Interest Configuration", {'lender':self.lender, 'from_amount':['<=',self.balance], 'to_amount':['>=',self.balance]}, ['rebait_threshold'])
		return rebate_threshold
	
	def get_rebate_interest_percent(self):
		rebate_interest = frappe.db.get_value("Interest Configuration", {'lender':self.lender, 'from_amount':['<=',self.balance], 'to_amount':['>=',self.balance]}, ['rebait_interest'])
		return rebate_interest
	
	def check_for_additional_interest(self):
		# monthly scheduler - executes at start of month
		current_date = datetime.now()-timedelta(days=1)
		
		# check for additional interest transaction entry
		check_if_exist = frappe.db.sql("select * from `tabLoan Transaction` where loan='{}' and lender='{}' and transaction_type='Interests' and is_paid=0 order by time desc limit 1".format(self.name, self.lender), as_dict=1)

		if check_if_exist:
			# check if days spent greater than rebate threshold
			rebate_threshold = int(self.get_rebate_threshold())
			
			if current_date > (check_if_exist[0]['time'] + timedelta(days=rebate_threshold)):
				rebate_interest = self.get_rebate_interest_percent()
				amount = self.balance * rebate_interest / 100

				additional_interest_transaction = frappe.get_doc({
					'doctype': 'Loan Transaction',
					'loan': self.name,
					'lender': self.lender,
					'transaction_type': 'Additional Interests',
					'record_type': 'DR',
					'amount': amount,
					'time': current_date.replace(hour=23, minute=59, second=59, microsecond=999999),
				})
				additional_interest_transaction.save(ignore_permissions=True)
				frappe.db.commit()
				return additional_interest_transaction

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

@frappe.whitelist()
def add_virtual_interest(loan_name, input_date=None):
	frappe.enqueue_doc("Loan", loan_name, method="add_virtual_interest", input_date=input_date)

def add_virtual_interest_for_chunk(chunk_loans):
	for loan in chunk_loans:
		frappe.enqueue_doc("Loan", loan.name, method="add_virtual_interest")

@frappe.whitelist()
def add_all_virtual_interests():
	chunks = lms.chunk_doctype(doctype='Loan', limit=10)

	for start in chunks.get('chunks'):
		all_loans = frappe.db.get_all('Loan', limit_page_length=chunks.get('limit'), limit_start=start)
		
		frappe.enqueue(
			method='lms.lms.doctype.loan.loan.add_virtual_interest_for_chunk', 
			chunk_loans=[loan for loan in all_loans], 
			queue='long'
		)

@frappe.whitelist()
def book_all_virtual_interest_for_month(loan_name, input_date=None):
	frappe.enqueue_doc("Loan", loan_name, method="book_all_virtual_interest_for_month", input_date=input_date)

def create_loans_interest_transaction(loans):
	for loan in loans:
		frappe.enqueue_doc("Loan", loan.name, method="create_interest_transaction") 

@frappe.whitelist()
def create_all_loans_interest_transaction():
	chunks = lms.chunk_doctype(doctype='Loan', limit=10)

	for start in chunks.get('chunks'):
		all_loans = frappe.db.get_all('Loan', limit_page_length=chunks.get('limit'), limit_start=start)
		
		frappe.enqueue(
			method='lms.lms.doctype.loan.loan.create_loans_interest_transaction', 
			loans=[loan for loan in all_loans], 
			queue='long'
		)

def check_loans_for_additional_interest(loans):
	for loan in loans:
		frappe.enqueue_doc("Loan", loan.name, method="check_for_additional_interest")
		
@frappe.whitelist()
def check_all_loans_for_additional_interest():
	chunks = lms.chunk_doctype(doctype='Loan', limit=10)

	for start in chunks.get('chunks'):
		all_loans = frappe.db.get_all('Loan', limit_page_length=chunks.get('limit'), limit_start=start)
		
		frappe.enqueue(
			method='lms.lms.doctype.loan.loan.check_loans_for_additional_interest', 
			chunk_loans=[loan for loan in all_loans], 
			queue='long'
		)