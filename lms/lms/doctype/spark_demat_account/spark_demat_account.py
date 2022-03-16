# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document


class SparkDematAccount(Document):
    def validate(self):
        regex = "^(?=.*[a-zA-Z])(?=.*[0-9])[A-Za-z0-9]+$"
        p = re.compile(regex)
        if (re.search(p, self.dpid)) and (re.search(p, self.client_id)):
            pass
        else:
            frappe.throw("Special Characters not allowed")
