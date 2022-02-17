# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document


class SparkBankBranch(Document):
    def validate(self):
        self.get_ifsc()

    def get_ifsc(self):
        doc = frappe.get_doc("Spark Bank Branch", self.bank)
        num = ["^[a-zA-Z0-9_]*$"]
        match = re.match(num)
        if match:
            return True
        else:
            frappe.msgprint(
                ("Special Characters not allowed for this {0}").format(doc.ifsc)
            )
