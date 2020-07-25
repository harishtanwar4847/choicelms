# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class UserKYCChangeApplication(Document):
	def on_update(self):
		if self.status == 'Approved':
			for change in self.changes:
				frappe.db.set_value('User KYC', self.user_kyc, change.parameter, change.new_value)
