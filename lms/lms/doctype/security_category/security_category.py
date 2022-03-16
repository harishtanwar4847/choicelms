# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe import _
from frappe.model.document import Document


class SecurityCategory(Document):
    def before_save(self):
        already_exist = frappe.db.count(
            "Security Category",
            filters={"category_name": self.category_name, "lender": self.lender},
        )
        if already_exist >= 1:
            frappe.throw(
                _(
                    "Category name '{}' already exist for {} lender".format(
                        self.category_name, self.lender
                    )
                )
            )
