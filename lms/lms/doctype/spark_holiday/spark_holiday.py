# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SparkHoliday(Document):
    def validate(self):
        duplicate_date = frappe.get_value(self.doctype, {"date": self.date}, "name")
        if duplicate_date:
            frappe.throw("This Date already exists.")
