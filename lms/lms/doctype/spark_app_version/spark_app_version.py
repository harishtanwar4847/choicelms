# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document


class SparkAppVersion(Document):
    def on_update(self):
        if self.is_live:
            frappe.db.sql(
                "update `tabSpark App Version` set is_live=0 where name != '{}'".format(
                    self.name
                )
            )
