# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from lms.firebase import FirebaseAdmin
import lms

class LoanApplication(Document):
	def on_update(self):
		if self.status == 'Approved':
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
				'items': items,
			})
			loan.insert(ignore_permissions=True)

			username = frappe.db.get_value('User', {'owner': loan.owner}, 'username')
			frappe.db.set_value("Customer", {"user": username}, "loan_open", 1)
			fa = FirebaseAdmin()
			fa.send_data(
				data={'customer': lms.get_customer(username).as_json()},
				tokens=lms.get_firebase_tokens(username)
			)