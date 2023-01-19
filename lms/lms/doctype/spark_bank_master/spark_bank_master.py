# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SparkBankMaster(Document):
    def on_update(self):
        bank_branches = frappe.get_all("Spark Bank Branch", {"bank": self.name})
        if bank_branches:
            if self.is_active:
                for bank_branch in bank_branches:
                    bank_branch = frappe.get_doc("Spark Bank Branch", bank_branch.name)
                    bank_branch.is_active = 1
                    bank_branch.save(ignore_permissions=True)
                    frappe.db.commit()
            else:
                for bank_branch in bank_branches:
                    bank_branch = frappe.get_doc("Spark Bank Branch", bank_branch.name)
                    bank_branch.is_active = 0
                    bank_branch.save(ignore_permissions=True)
                    frappe.db.commit()
