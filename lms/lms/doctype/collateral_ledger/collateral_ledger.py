# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class CollateralLedger(Document):
    @staticmethod
    def create_entry(
        doctype, docname, request_type, psn, isin, quantity, loan_name=None, data=None
    ):
        doc = frappe.get_doc(doctype, docname)
        collateral_ledger = frappe.get_doc(
            {
                "doctype": "Collateral Ledger",
                "customer": doc.customer,
                "lender": doc.lender,
                "request_type": request_type,
                "isin": isin,
                "quantity": quantity,
                "application_doctype": doctype,
                "application_name": docname,
                "psn": psn,
            }
        )

        if loan_name:
            collateral_ledger.loan = loan_name

        if request_type == "Pledge":
            data = frappe._dict(data)
            collateral_ledger.prf = data.prf
            collateral_ledger.expiry = data.expiry
            collateral_ledger.pledgor_boid = data.pledgor_boid
            collateral_ledger.pledgee_boid = data.pledgee_boid

        collateral_ledger.save(ignore_permissions=True)
        frappe.db.commit()
