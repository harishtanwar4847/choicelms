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

        if self.sell_off_deadline_eod > 24:
            frappe.throw("Please keep the value for EOD below 24.")
