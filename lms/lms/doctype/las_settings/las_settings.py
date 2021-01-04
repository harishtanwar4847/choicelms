# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document


class LASSettings(Document):
    def before_save(self):
        if self.loan_margin == 0:
            frappe.throw(_("Loan margin can not be 0."))

        if self.loan_interest == 0:
            frappe.throw(_("Loan interest can not be 0."))

    def cdsl_headers(self):
        return {
            "Referer": self.cdsl_referrer,
            "DPID": self.cdsl_dpid,
            "UserID": self.cdsl_user_id,
            "Password": self.cdsl_password,
        }
