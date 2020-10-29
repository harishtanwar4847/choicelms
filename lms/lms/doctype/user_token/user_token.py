# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.core.doctype.sms_settings.sms_settings import send_sms
import lms

class UserToken(Document):
	def after_insert(self):
		if not frappe.flags.in_test:
			if self.token_type in ['OTP', 'Pledge OTP']:
				las_settings = frappe.get_single('LAS Settings')	
				if self.token_type == 'OTP':
					mess = frappe._('Your OTP for LMS is {}. Do not share your OTP with anyone.{}').format(self.token, las_settings.app_identification_hash_string)
				elif self.token_type == 'Pledge OTP':
					mess = frappe._('Your Pledge OTP for LMS is {}. \nDo not share your Pledge OTP with anyone.{}').format(self.token, las_settings.app_identification_hash_string)
				frappe.enqueue(method=send_sms, receiver_list=[self.entity], msg=mess)
			elif self.token_type == "Email Verification Token":
				doc=frappe.get_doc('User', self.entity).as_dict()
				doc["url"] = frappe.utils.get_url("/api/method/lms.auth.verify_user?token={}&user={}".format(self.token, self.entity))
				frappe.enqueue_doc('Notification', 'User Email Verification', method='send', doc=doc)


