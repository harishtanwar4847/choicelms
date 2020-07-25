# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class ConcentrationRule(Document):
	def validate(self):
		self.validate_percentage_values()

	def validate_percentage_values(self):
		valid = True

		# check single script threshold
		if self.is_single_script_allowed and self.single_script_threshold_type == "Percentage" and self.single_script_threshold > 100.00:
			valid = False

		# check per script threshold
		if valid and self.is_group_script_limited and self.per_script_threshold_type == "Percentage" and self.per_script_threshold > 100.00:
			valid = False

		# check group script threshold
		if valid and self.is_group_script_limited and self.group_script_threshold_type == "Percentage" and self.group_script_threshold > 100.00:
			valid = False

		# check group max limit
		if valid and self.is_group_script_max_limited and self.group_script_max_limit_type == "Percentage" and self.group_script_max_limit > 100.00:
			valid = False

		if not valid:
			frappe.throw("Percentage values should not exceed 100.")

