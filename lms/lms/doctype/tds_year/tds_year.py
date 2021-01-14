# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import datetime

import frappe
from frappe.model.document import Document


class TDSYear(Document):
    def before_insert(self):
        now = datetime.datetime.now()
        year = now.year
        tdsYear = frappe.db.count("TDS Year", {"is_active": 1})
        print(tdsYear)
        if tdsYear == 2:
            frappe.throw("At a time only two entries can be active")
