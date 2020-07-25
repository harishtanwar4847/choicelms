# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document

class UserKYC(Document):
	def before_save(self):
		new_dict = self.as_dict()
		old_dict = frappe.get_doc('User KYC', self.name).as_dict()
		changes = []
		if '__islocal' not in new_dict.keys():
			for key in new_dict.keys():
				if key not in ['creation', 'modified']:
					if new_dict[key] != old_dict[key]:
						changes.append({
							'parameter': key, 
							'old_value': old_dict[key], 
							'new_value': new_dict[key]
						})

			if len(changes) == 0:
				frappe.throw(_('No changes'))

			user_kyc_change_application = frappe.get_doc({
				'doctype': 'User KYC Change Application',
				'user_kyc': self.name,
				'changes': changes
			})
			user_kyc_change_application.insert(ignore_permissions=True)
			frappe.db.commit()
			frappe.throw(_('User KYC Change Application {} created').format(user_kyc_change_application.name))
