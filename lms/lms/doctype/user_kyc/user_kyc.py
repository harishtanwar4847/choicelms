# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document

import lms


class UserKYC(Document):
    def on_update(self):
        if self.kyc_status == "Approved":
            cust_name = frappe.db.get_value(
                "Loan Customer", {"user": self.user}, "name"
            )
            loan_customer = frappe.get_doc("Loan Customer", cust_name)
            if not loan_customer.kyc_update and not loan_customer.choice_kyc:
                loan_customer.kyc_update = 1
                loan_customer.choice_kyc = self.name
                loan_customer.save(ignore_permissions=True)
                frappe.db.commit()
