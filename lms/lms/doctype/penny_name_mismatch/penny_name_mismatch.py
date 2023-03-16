# Copyright (c) 2023, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PennyNameMismatch(Document):
    def onload(self):
        if not self.seen:
            self.db_set("seen", 1, update_modified=0)
            frappe.db.commit()
