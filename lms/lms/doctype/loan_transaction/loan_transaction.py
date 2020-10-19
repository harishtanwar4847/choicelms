# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _

class LoanTransaction(Document):
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
		frappe.enqueue_doc('Loan', self.loan, method='check_for_shortfall')

		lender_doc = frappe.get_doc("Lender", "LENDER000001").as_dict()
		# variable defined for fixed loan transactions
		charges_sharing_details = {
			'Processing Fees': {
				"type_field":"lender_processing_fees_sharing_type",
				"value_field":"lender_processing_fees_sharing",
				"label":'Processing Fees'
			},
			'Stamp Duty': {
				"type_field":"stamp_duty_sharing_type",
				"value_field":"stamp_duty_sharing",
				"label":'Stamp Duty'
			},
			'Documentation Charges': {
				"type_field":"documentation_charge_sharing_type",
				"value_field":"documentation_charges_sharing",
				"label":'Documentation Charges'
			},
			'Mortgage Charges': {
				"type_field":"mortgage_charge_sharing_type",
				"value_field":"mortgage_charges_sharing",
				"label":'Mortgage Charges'
			},
		}

		spark_amount = lender_amount = 0

		# transaction_charges_sharing_obj = next(item for item in charges_sharing_details if item['label'] == self.transaction_type)
		transaction_charges_sharing_obj = charges_sharing_details.get(self.transaction_type, None)
		if transaction_charges_sharing_obj:
			if lender_doc[transaction_charges_sharing_obj["type_field"]] == "Percentage":
				lender_amount = (self.amount*lender_doc[transaction_charges_sharing_obj['value_field']])/100
			else:
				lender_amount = self.amount - lender_doc[transaction_charges_sharing_obj['value_field']]
				
			spark_amount = self.amount - lender_amount

			# add loan spark/lender ledger document entry
			spark_ledger_doc = frappe.get_doc({
				'doctype': 'Lender Ledger',
				'loan': self.loan,
				'loan_transaction':self.name,
				'share_owner':'Spark',
				'lender':'',
				'amount':spark_amount,
			})
			spark_ledger_doc.insert(ignore_permissions=True)

			lender_ledger_doc = frappe.get_doc({
				'doctype': 'Lender Ledger',
				'loan': self.loan,
				'loan_transaction':self.name,
				'share_owner':'Lender',
				'lender':lender_doc.name,
				'amount':lender_amount,
			})
			lender_ledger_doc.insert(ignore_permissions=True)
