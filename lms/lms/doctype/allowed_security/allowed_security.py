# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document

import lms


class AllowedSecurity(Document):
    def before_save(self):
        self.security_name = frappe.db.get_value("Security", self.isin, "security_name")
