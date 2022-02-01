# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SparkHoliday(Document):
    pass
    # def validate(self):
    #     duplicate_date = frappe.get_value(self.doctype, {"date": self.date}, "name")
    #     if duplicate_date:
    #         frappe.throw("This Date already exists.")

    # def on_update(self):
    #     self.update_margin_shortfall_deadline()

    # def update_margin_shortfall_deadline(self):
    #     loan_margin_shortfall = frappe.get_all("Loan Margin Shortfall", {"status": ["Pending","Request Pending"]})
    #     if loan_margin_shortfall:
    #         for single_margin_shortfall in loan_margin_shortfall:
    #             single_margin_shortfall = frappe.get_doc("Loan Margin Shortfall", single_margin_shortfall.name)
    #             single_margin_shortfall.update_deadline_based_on_holidays()
    #             single_margin_shortfall.save(ignore_permissions=True)
    #             frappe.db.commit()
