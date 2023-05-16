# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SparkHoliday(Document):
    def on_update(self):
        self.update_margin_shortfall_deadline()

    def on_trash(self):
        self.update_margin_shortfall_deadline()

    def update_margin_shortfall_deadline(self):
        loan_margin_shortfall = frappe.get_list(
            "Loan Margin Shortfall",
            {"status": ["in", ["Pending", "Request Pending"]]},
            "name",
        )
        if loan_margin_shortfall:
            for single_margin_shortfall in loan_margin_shortfall:
                single_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", single_margin_shortfall
                )
                single_margin_shortfall.update_deadline_based_on_holidays()
                single_margin_shortfall.save(ignore_permissions=True)
                frappe.db.commit()
