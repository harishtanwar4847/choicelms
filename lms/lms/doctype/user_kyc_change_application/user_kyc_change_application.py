# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class UserKYCChangeApplication(Document):
	def after_save(self):
		if self.status == 'Approved':
			user_kyc = frappe.get_doc('User KYC', self.user_kyc)

			for change in self.changes:
				user_kyc[change.paremeter] = change.new_value

			user_kyc.save(ignore_permissions=True)
