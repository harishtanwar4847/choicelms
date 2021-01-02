# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class LoanWithdrawLedger(Document):
    def after_insert(self):
        self.update_loan()

    def update_loan(self):
        outstanding = 0
        filters = {"loan": self.loan}

        withdraw_ledger_list = frappe.get_all(
            "Loan Withdraw Ledger",
            filters=filters,
            page_length=frappe.db.count("Loan Withdraw Ledger", filters=filters),
            fields=["amount", "name"],
        )

        for i in withdraw_ledger_list:
            outstanding += i.amount

        loan = frappe.get_doc("Loan", self.loan)
        loan.outstanding = outstanding
        loan.save(ignore_permissions=True)
        frappe.db.commit()
