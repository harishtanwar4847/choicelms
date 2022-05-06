# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AMCDetails(Document):
    def before_save(self):
        self.security_name = frappe.db.get_value(
            "Security", self.security, "security_name"
        )
