# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class Customer(Document):
	def before_save(self):
		user = frappe.get_doc('User', self.username)

		self.first_name = user.first_name
		self.middle_name = user.middle_name
		self.last_name = user.last_name
		self.full_name = user.full_name
		self.email = user.email
		self.phone = user.phone
		self.owner = user.email
		self.registeration = 1