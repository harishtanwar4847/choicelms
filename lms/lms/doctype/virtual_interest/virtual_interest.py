# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime

import frappe
from frappe.model.document import Document

import lms


class VirtualInterest(Document):
    pass


def get_permission_query_conditions(user):
    if not user:
        user = frappe.session.user

    if "System Manager" in frappe.get_roles(user):
        return None
    elif "Lender" in frappe.get_roles(user):
        roles = frappe.get_roles(user)

        return """(`tabLoan`.lender in {role_tuple})""".format(
            role_tuple=lms.convert_list_to_tuple_string(roles)
        )
