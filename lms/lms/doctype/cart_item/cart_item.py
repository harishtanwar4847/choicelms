# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class CartItem(Document):
	def fill_item_details(self):
		security = frappe.get_doc("Allowed Security", self.isin)
		self.security_category = security.category
		self.security_name = security.security_name
		self.eligible_percentage = security.eligible_percentage

		price_list = frappe.get_all(
			'Security Price', 
			filters={'security': self.isin}, 
			order_by='time desc', 
			limit_page_length=1, 
			fields=['name', 'price']
		)
		self.price = price_list[0].price
		self.amount = self.pledged_quantity * self.price

	def get_concentration_rule(self):
		return frappe.get_doc("Concentration Rule", self.security_category)
