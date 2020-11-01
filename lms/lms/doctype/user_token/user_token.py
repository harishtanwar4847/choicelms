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
			if self.token_type in ['OTP', 'Pledge OTP', 'Withdraw OTP']:
				las_settings = frappe.get_single('LAS Settings')
				mess = frappe._('Your {token_type} for LMS is {token}. Do not share your {token_type} with anyone.{app_hash_string}').format(token_type=self.token_type, token=self.token, app_hash_string=las_settings.app_identification_hash_string)
				frappe.enqueue(method=send_sms, receiver_list=[self.entity], msg=mess)
			elif self.token_type == "Email Verification Token":
				doc=frappe.get_doc('User', self.entity).as_dict()
				doc["url"] = frappe.utils.get_url("/api/method/lms.auth.verify_user?token={}&user={}".format(self.token, self.entity))
				frappe.enqueue_doc('Notification', 'User Email Verification', method='send', doc=doc)


