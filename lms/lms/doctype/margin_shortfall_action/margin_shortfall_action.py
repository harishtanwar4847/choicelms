# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class MarginShortfallAction(Document):
    def before_save(self):
        if self.sell_off_after_hours and self.sell_off_deadline_eod:
            frappe.throw("Please put value at sell off deadline either EOD or in hours")

        if self.sell_off_after_hours < 0 or self.sell_off_deadline_eod < 0:
            frappe.throw("Please provide valid input")

        if self.sell_off_deadline_eod > 24:
            frappe.throw("Please keep the value for EOD between 1 to 24.")

        if self.sell_off_after_hours:
            if self.sell_off_after_hours < 24 or self.sell_off_after_hours % 24 != 0:
                frappe.throw("Sell Off Deadline (in hours) should be in multiple of 24")
