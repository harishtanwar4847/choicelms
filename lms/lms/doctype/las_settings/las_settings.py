# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document


class LASSettings(Document):
    def cdsl_headers(self):
        return {
            "Referer": self.cdsl_referrer,
            "DPID": self.cdsl_dpid,
            "UserID": self.cdsl_user_id,
            "Password": self.cdsl_password,
        }

    def get_spark_logo_file(self):
        file_name = frappe.db.get_value("File", {"file_url": self.spark_logo})
        return frappe.get_doc("File", file_name) if file_name else None

    def get_lender_template(self):
        file_name = frappe.db.get_value("File", {"file_url": self.lender_template})
        return frappe.get_doc("File", file_name)

    def get_approved_securities_template(self):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.approved_security_template}
        )
        return frappe.get_doc("File", file_name)

    def get_news_blog_template(self):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.news_and_blog_template}
        )
        return frappe.get_doc("File", file_name)
