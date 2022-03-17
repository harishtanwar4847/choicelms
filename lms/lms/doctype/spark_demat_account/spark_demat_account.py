# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document

import lms


class SparkDematAccount(Document):
    def validate(self):
        reg = lms.regex_special_characters(
            search=self.get("dpid") + self.get("client_id")
        )
        if reg == True:
            frappe.throw("Special Characters not allowed")
