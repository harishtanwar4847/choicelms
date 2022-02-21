# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
import utils
from frappe.model.document import Document

import lms


class SparkBankBranch(Document):
    def validate(self):
        self.get_bank_branch()
        # self.get_district()
        # self.get_city()
        # self.get_state()

    def get_bank_branch(self):
        is_alphanumeric = lms.regex_special_characters(
            search=self.ifsc, regex=re.compile("^[a-zA-Z0-9]*$")
        )
        if not is_alphanumeric:
            frappe.throw("Only Alphanumeric value are allowed.")

        is_alphanumeric = lms.regex_special_characters(
            search=self.district, regex=re.compile("^[a-zA-Z0-9]*$")
        )
        if not is_alphanumeric:
            frappe.throw("Only Alphanumeric value are allowed.")

        is_alphanumeric = lms.regex_special_characters(
            search=self.city, regex=re.compile("^[a-zA-Z0-9]*$")
        )
        if not is_alphanumeric:
            frappe.throw("Only Alphanumeric value are allowed.")

        is_alphanumeric = lms.regex_special_characters(
            search=self.state, regex=re.compile("^[a-zA-Z0-9]*$")
        )
        if not is_alphanumeric:
            frappe.throw("Only Alphanumeric value are allowed.")
