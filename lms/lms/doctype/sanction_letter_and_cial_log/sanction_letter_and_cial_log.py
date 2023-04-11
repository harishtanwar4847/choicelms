# Copyright (c) 2023, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SanctionLetterandCIALLog(Document):
    def validate(self):
        for i, item in enumerate(
            sorted(self.interest_letter_table, key=lambda item: item.creation), start=1
        ):
            item.idx = i
