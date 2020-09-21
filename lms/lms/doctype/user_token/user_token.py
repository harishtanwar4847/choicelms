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
		if self.token_type in ['OTP', 'Pledge OTP']:
			if self.token_type == 'OTP':
				mess = frappe._('Your OTP for LMS is {0}. Do not share your OTP with anyone.').format(self.token)
			elif self.token_type == 'Pledge OTP':
				user = frappe.get_doc('User', lms.get_user(self.entity))
				mess = frappe._('Your Pledge OTP for LMS is {0}. Do not share your Pledge OTP with anyone.').format(self.token)
			frappe.enqueue(method=send_sms, receiver_list=[self.entity if self.token_type == 'OTP' else user.username], msg=mess)
		elif self.token_type == "Email Verification Token":
			template = "/templates/emails/user_email_verification.html"
			url = frappe.utils.get_url("/api/method/lms.auth.verify_user?token={}&user={}".format(self.token, self.entity))

			frappe.enqueue(
				method=frappe.sendmail, 
				recipients=self.entity, 
				sender=None, 
				subject="Email Verification",
				message=frappe.get_template(template).render(url=url)
			)