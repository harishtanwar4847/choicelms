# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import cint
from frappe import _

class Lender(Document):
	def validate(self):
		if cint(self.interest_percentage_sharing) > 100:
			frappe.throw(_('Interest Percentage Sharing value should not greater than 100.'))
		
		if self.lender_processing_fees_type == "Percentage" and cint(self.lender_processing_fees) > 100:
			frappe.throw(_('Lender Processing Fees value should not greater than 100.'))

		if self.stamp_duty_type == "Percentage" and cint(self.stamp_duty) > 100:
			frappe.throw(_('Stamp Duty value should not greater than 100.'))
			
		if self.documentation_charge_type == "Percentage" and cint(self.documentation_charges) > 100:
			frappe.throw(_('Documentation Charges value should not greater than 100.'))
		
		if self.mortgage_charge_type == "Percentage" and cint(self.mortgage_charges) > 100:
			frappe.throw(_('Mortgage Charges value should not greater than 100.'))
		
		if self.lender_processing_fees_sharing_type == "Percentage" and cint(self.lender_processing_fees_sharing) > 100:
			frappe.throw(_('Lender Processing Fees Sharing value should not greater than 100.'))

		if self.stamp_duty_sharing_type == "Percentage" and cint(self.stamp_duty_sharing) > 100:
			frappe.throw(_('Stamp Duty Sharing value should not greater than 100.'))
			
		if self.documentation_charge_sharing_type == "Percentage" and cint(self.documentation_charges_sharing) > 100:
			frappe.throw(_('Documentation Charges Sharing value should not greater than 100.'))
		
		if self.mortgage_charge_sharing_type == "Percentage" and cint(self.mortgage_charges_sharing) > 100:
			frappe.throw(_('Mortgage Charges Sharing value should not greater than 100.'))
		
def get_permission_query_conditions(user):
	if not user: user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None
	elif "Lender" in frappe.get_roles(user):
		roles = frappe.get_roles(user)

		return """(`tabLender`.full_name in {role_tuple})"""\
			.format(role_tuple=lms.convert_list_to_tuple_string(roles))