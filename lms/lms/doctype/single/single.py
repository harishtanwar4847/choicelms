# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class single(Document):
    def on_update(self):
        self.single_value()

    def single_value(self):
        doc = frappe.db.get_single_value("single", "number")
        frappe.msgprint(("Single value is{0}").format(doc))
