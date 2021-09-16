import frappe
import utils

import lms

@frappe.whitelist(allow_guest=True)
def fetch_related_shares(lender_name):
    len_name = lender_name.replace("%20", " ")
    lender_data = frappe.db.sql("select * from `tabLender` where name = '{}'".format(len_name), as_dict = 1)
    interest_config = frappe.db.sql("select * from `tabInterest Configuration` where lender = '{}'".format(len_name), as_dict = 1)
    response = {"lender_data": lender_data, 'interest_config':interest_config}

    return utils.respondWithSuccess(data=response)
