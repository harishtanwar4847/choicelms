# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
import utils
from frappe.model.document import Document

import lms


class SparkBankBranch(Document):
    def validate(self):
        self.get_bank_details()

    def get_bank_details(self):
        if self.ifsc:
            check_ifsc = lms.regex_special_characters(
                search=self.ifsc, regex=re.compile("^[a-zA-Z0-9]*$")
            )
            if not check_ifsc:
                frappe.throw("Only Alphanumeric value are allowed.")
