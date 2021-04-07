# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class CollateralLedger(Document):
    @staticmethod
    def create_entry(doctype, docname, request_type, isin, quantity, data):
        doc = frappe.get_doc(doctype, docname)
        collateral_ledger = frappe.get_doc(
            {
                "doctype": "Collateral Ledger",
                "customer": doc.customer,
                "lender": doc.lender,
                "request_type": request_type,
                "isin": isin,
                "quantity": quantity,
            }
        )

        if doctype == "Loan Application":
            collateral_ledger.loan_application = docname
        if doctype == "Loan":
            collateral_ledger.loan = docname

        if request_type == "Pledge":
            data = frappe._dict(data)
            collateral_ledger.prf = data.prf
            collateral_ledger.expiry = data.expiry
            collateral_ledger.pledgor_boid = data.pledgor_boid
            collateral_ledger.pledgee_boid = data.pledgee_boid
            collateral_ledger.psn = data.psn

        collateral_ledger.save(ignore_permissions=True)
