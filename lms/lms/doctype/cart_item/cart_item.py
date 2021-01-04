# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document

import lms


class CartItem(Document):
    def fill_item_details(self):
        security = frappe.get_doc("Allowed Security", self.isin)
        self.security_category = security.category
        self.security_name = security.security_name
        self.eligible_percentage = security.eligible_percentage

        price_map = lms.get_security_prices([self.isin])
        self.price = price_map.get(self.isin, 0)
        self.amount = self.pledged_quantity * self.price

    def get_concentration_rule(self):
        return frappe.get_doc("Concentration Rule", self.security_category)
