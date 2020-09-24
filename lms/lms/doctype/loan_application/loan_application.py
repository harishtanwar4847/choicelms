# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.core.doctype.sms_settings.sms_settings import send_sms

class LoanApplication(Document):
	def on_update(self):
		if self.status == 'Approved':
			if not self.loan:
				self.create_loan()
			else:
				self.update_existing_loan()

	def create_loan(self):
		items = []

		for item in self.items:
			temp = frappe.get_doc({
				'doctype': 'Loan Item',
				'isin': item.isin,
				'security_name': item.security_name,
				'security_category': item.security_category,
				'pledged_quantity': item.pledged_quantity,
				'price': item.price,
				'amount': item.amount,
				'psn': item.psn,
				'error_code': item.error_code,
			})

			items.append(temp)

		loan = frappe.get_doc({
			'doctype': 'Loan',
			'total_collateral_value': self.total_collateral_value,
			'overdraft_limit': self.overdraft_limit,
			'pledgor_boid': self.pledgor_boid,
			'prf_number': self.prf_number,
			'pledgee_boid': self.pledgee_boid,
			'expiry_date': self.expiry_date,
			'allowable_ltv': self.allowable_ltv,
			'customer': self.customer,
			'items': items,
		})
		loan.insert(ignore_permissions=True)

		customer = frappe.db.get_value('Customer', {'name': self.customer}, 'username')
		doc = frappe.get_doc('User', customer)
		frappe.enqueue_doc('Notification', 'Loan Sanction', method='send', doc=doc)

		mobile = frappe.db.get_value('Customer', {'name': self.customer}, 'user')
		mess = _("Dear " + doc.full_name + ", \nCongratulations! Your loan account is active now! \nCurrent available limit - " + str(loan.overdraft_limit) + ".")
		frappe.enqueue(method=send_sms, receiver_list=[mobile], msg=mess)

		customer = frappe.get_doc('Customer', self.customer)
		if not customer.loan_open:
			customer.loan_open = 1
			customer.save(ignore_permissions=True)

	def update_existing_loan(self):
		loan = frappe.get_doc('Loan', self.loan)

		for item in self.items:
			loan.append('items', {
				'isin': item.isin,
				'security_name': item.security_name,
				'security_category': item.security_category,
				'pledged_quantity': item.pledged_quantity,
				'price': item.price,
				'amount': item.amount,
				'psn': item.psn,
				'error_code': item.error_code,
			})

		loan.total_collateral_value += self.total_collateral_value
		loan.overdraft_limit += self.overdraft_limit

		loan.save(ignore_permissions=True)