# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class ApprovedTermsandConditions(Document):
    @staticmethod
    def create_entry(doctype, docname, mobile, tnc, time):
        doc = frappe.get_doc(doctype, docname)
        approved_tnc = frappe.get_doc(
            {
                "doctype": "Approved Terms and Conditions",
                "application_doctype": doctype,
                "application_name": docname,
                "mobile": mobile,
                "tnc": tnc,
                "time": time,
            }
        )

        approved_tnc.save(ignore_permissions=True)
