# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
# import frappe
from frappe.model.document import Document

class LASSettings(Document):
	def cdsl_headers(self):
		return {
	 		"Referer": self.cdsl_referrer,
			"DPID": self.cdsl_dpid,
			"UserID": self.cdsl_user_id,
			"Password": self.cdsl_password
		}
