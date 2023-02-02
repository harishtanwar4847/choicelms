# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

# import frappe
import uuid

from frappe.model.document import Document


class LoanApplicationItem(Document):
    def autoname(self):
        self.name = uuid.uuid4()
        print(self.name, "loan application item name")
