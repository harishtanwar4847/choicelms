# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
import lms

class LoanTransaction(Document):
	def get_loan(self):
		return frappe.get_doc('Loan', self.loan)
	
	def before_insert(self):
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

	def after_insert(self):
		frappe.enqueue_doc('Loan', self.loan, method='update_loan_balance')
		frappe.enqueue_doc('Loan', self.loan, method='check_for_shortfall')

def get_permission_query_conditions(user):
	if not user: user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None
	elif "Lender" in frappe.get_roles(user):
		roles = frappe.get_roles(user)

		return """(`tabLoan Transaction`.lender in {role_tuple})"""\
			.format(role_tuple=lms.convert_list_to_tuple_string(roles))
