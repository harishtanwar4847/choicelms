# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document


class UserKYC(Document):
    # def before_save(self):
    #     new_dict = self.as_dict()
    #     if "__islocal" not in new_dict.keys():
    #         frappe.throw("Modifications not allowed.")
    pass
