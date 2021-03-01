# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class TopupApplication(Document):
    def on_update(self):
        loan = frappe.get_doc("Loan", self.loan)
        if self.status == "Approved":
            loan.drawing_power += self.top_up_amount
            loan.sanctioned_limit += self.top_up_amount
            loan.save(ignore_permissions=True)
