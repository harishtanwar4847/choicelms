# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class NewsandBlog(Document):
    def before_save(self):
        if not self.publishing_date:
            self.publishing_date = frappe.utils.today()
