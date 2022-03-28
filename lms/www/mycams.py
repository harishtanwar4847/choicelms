import frappe
import utils

import lms


def get_context(context):
    context.encrypted = frappe.form_dict.encrypted_data
