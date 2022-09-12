# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SparkAppVersion(Document):
    def before_save(self):
        if not self.is_live:
            live_count = frappe.db.count(
                "Spark App Version", filters={"is_live": 1, "name": ["!=", self.name]}
            )
            if not live_count:
                frappe.throw("At least one entry should be checked as Is Live")

    def on_update(self):
        if self.is_live:
            frappe.db.sql(
                "update `tabSpark App Version` set is_live=0 where name != '{}'".format(
                    self.name
                )
            )
