# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
import lms
from datetime import datetime

class LoanTransaction(Document):
	loan_transaction_map = {
		'Withdrawal': 'DR',
		'Payment': 'CR',
		'Debit Note': 'DR',
		'Credit Note': 'CR',
		'Processing Fees': 'DR',
		'Stamp Duty': 'DR',
		'Documentation Charges': 'DR',
		'Mortgage Charges': 'DR',
		'Sell Collateral': 'DR', # confirm
		'Invoke Pledge': 'DR', # confirm
		'Interest': 'DR',
		'Additional Interest': 'DR',
		'Penal Interest': 'DR',
		'Other Charges': 'DR'
	}

	def validate_withdrawal_amount(self):
		if self.amount <= 0:
			frappe.throw('Please fix the amount.')
		if self.transaction_type == 'Withdrawal':
			loan = self.get_loan()
			maximum_withdrawable_amount = loan.maximum_withdrawable_amount()
			if self.amount > maximum_withdrawable_amount:
				frappe.throw('Can not withdraw more than {}'.format(maximum_withdrawable_amount))

	def set_record_type(self):
		self.record_type = self.loan_transaction_map.get(self.transaction_type, 'DR')

	def get_loan(self):
		return frappe.get_doc('Loan', self.loan)

	def get_lender(self):
		return frappe.get_doc('Lender', self.lender)
	
	def before_insert(self):
		self.set_record_type()
		self.validate_withdrawal_amount()
		# check for user roles and permissions before adding transactions
		user_roles = frappe.db.get_values("Has Role", {"parent":frappe.session.user, "parenttype": "User"},["role"])
		if not user_roles:
			frappe.throw(_('Invalid User'))
		user_roles = [role[0] for role in user_roles]
		
		loan_cust_transaction_list = ["Withdrawal", "Payment", "Sell Collateral"]
		lender_team_transaction_list = ["Debit Note", "Credit Note", "Processing Fees", "Stamp Duty", "Documentation Charges", "Mortgage Charges", "Invoke Pledge", "Interests", "Additional Interests", "Other Charges"]
		
		if "System Manager" not in user_roles:
			if self.transaction_type in loan_cust_transaction_list and ("Loan Customer" not in user_roles):
				frappe.throw(_('You are not permitted to perform this action'))
			elif self.transaction_type in lender_team_transaction_list and ("Lender Team" not in user_roles):
				frappe.throw(_('You are not permitted to perform this action'))

	def on_submit(self):
		if self.transaction_type in ['Processing Fees', 'Stamp Duty', 'Documentation Charges', 'Mortgage Charges']:
			lender = self.get_lender()
			
			if self.transaction_type == 'Processing Fees':
				sharing_amount = lender.lender_processing_fees_sharing
				sharing_type = lender.lender_processing_fees_sharing_type
			elif self.transaction_type == 'Stamp Duty':
				sharing_amount = lender.stamp_duty_sharing
				sharing_type = lender.stamp_duty_sharing_type
			elif self.transaction_type == 'Documentation Charges':
				sharing_amount = lender.documentation_charges_sharing
				sharing_type = lender.documentation_charge_sharing_type
			elif self.transaction_type == 'Mortgage Charges':
				sharing_amount = lender.mortgage_charges_sharing
				sharing_type = lender.mortgage_charge_sharing_type

			lender_sharing_amount = sharing_amount
			if sharing_type == 'Percentage':
				lender_sharing_amount = (lender_sharing_amount/100) * self.amount
			spark_sharing_amount = self.amount - lender_sharing_amount
			self.create_lender_ledger(self.name, lender_sharing_amount, spark_sharing_amount)

		loan = self.get_loan()
		loan.update_loan_balance()
		
		if self.loan_margin_shortfall:
			loan_margin_shortfall = frappe.get_doc('Loan Margin Shortfall', self.loan_margin_shortfall)
			loan_margin_shortfall.fill_items()
			if not loan_margin_shortfall.margin_shortfall_action:
				loan_margin_shortfall.status = 'Paid Cash'
				loan_margin_shortfall.action_time = datetime.now()
			loan_margin_shortfall.save(ignore_permissions=True)

		if self.is_for_interest:
			# fetch all interest transaction which are not paid 
			# sauce: https://stackoverflow.com/a/25433139/9403680
			not_paid_interests = frappe.db.sql('''select name, amount, time, unpaid_interest, transaction_type from `tabLoan Transaction` where loan=%s and transaction_type in ('Interest', 'Additional Interest', 'Penal Interest') and unpaid_interest > 0 order by field(transaction_type, "Penal Interest", "Additional Interest", "Interest")''', self.loan, as_dict=1)

			if not_paid_interests:
				total_interest_amt_paid = self.amount
				for interest in not_paid_interests:
					interest_pay_log_amt = unpaid_interest = 0

					if interest['unpaid_interest'] > total_interest_amt_paid:
						interest_pay_log_amt = total_interest_amt_paid
						unpaid_interest = interest['unpaid_interest'] - total_interest_amt_paid
						total_interest_amt_paid = 0

					if interest['unpaid_interest'] <= total_interest_amt_paid:
						interest_pay_log_amt = interest['unpaid_interest']
						unpaid_interest = 0
						total_interest_amt_paid = total_interest_amt_paid - interest['unpaid_interest']

					# Add 'Interest pay log' entry and also Update 'unpaid_interest' 
					interest_doc = frappe.get_doc("Loan Transaction", interest['name'])
					interest_doc.append('items', {
						'amount': interest_pay_log_amt,
						'payment_transaction':self.name
					})
					interest_doc.save(ignore_permissions=True)
					interest_doc.db_set('unpaid_interest', unpaid_interest)
					
					if total_interest_amt_paid <= 0:
						break

	def create_lender_ledger(self, loan_transaction_name, lender_share, spark_share):
		frappe.get_doc({
			'doctype': 'Lender Ledger',
			'loan': self.loan,
			'loan_transaction': self.name,
			'lender': self.lender,
			'amount': self.amount,
			'lender_share': lender_share,
			'spark_share': spark_share,
		}).insert(ignore_permissions=True)

	def before_submit(self):
		if not self.transaction_id:
			frappe.throw('Kindly add transaction id before approving')

def get_permission_query_conditions(user):
	if not user: user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None
	elif "Lender" in frappe.get_roles(user):
		roles = frappe.get_roles(user)

		return """(`tabLoan Transaction`.lender in {role_tuple})"""\
			.format(role_tuple=lms.convert_list_to_tuple_string(roles))	