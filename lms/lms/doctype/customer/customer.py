# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from lms.firebase import FirebaseAdmin
import lms

class Customer(Document):
	def before_insert(self):
		user = frappe.get_doc('User', self.username)

		self.first_name = user.first_name
		self.middle_name = user.middle_name
		self.last_name = user.last_name
		self.full_name = user.full_name
		self.email = user.email
		self.phone = user.phone
		self.user = user.phone
		self.registeration = 1

	def on_update(self):
		user_kyc = {}
		if self.choice_kyc:
			user_kyc = frappe.get_doc("User KYC",self.choice_kyc).as_json()
			
		pending_esigns = frappe.get_all('Loan Application', filters={'customer': self.name, 'status': 'Pending'}, fields=['*'])

		fa = FirebaseAdmin()
		fa.send_data(
			data={
				'customer': self.as_json(),
				'user_kyc': user_kyc,
				'pending_esigns' : pending_esigns
			},
			tokens=lms.get_firebase_tokens(self.username)
		)