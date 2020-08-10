# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class CartItem(Document):
	def set_security_details(self):
		security = frappe.get_doc("Allowed Security", self.isin)
		self.security_category = security.category
		self.security_name = security.security_name

	def get_concentration_rule(self):
		return frappe.get_doc("Concentration Rule", self.security_category)
