import frappe
import utils

import lms


@frappe.whitelist(allow_guest=True)
def fetch_interest_config(lender_name):
    len_name = lender_name.replace("%20", " ")
    lender_data = frappe.db.sql(
        "select * from `tabLender` where name = '{}'".format(len_name), as_dict=1
    )
    interest_config = frappe.db.sql(
        "select * from `tabInterest Configuration` where lender = '{}' order by to_amount ".format(
            len_name
        ),
        as_dict=1,
    )
    lender_data[0]["default_interest"] = "{:.2f}".format(
        float((lender_data[0]["default_interest"]))
    )
    for interest in interest_config:
        interest["to_amount_str"] = lms.rupees_to_words(int((interest.to_amount)))
        interest["sum_interest"] = "{:.2f}".format(
            float((interest["rebait_interest"] + interest["base_interest"]))
        )
        interest["rebait_interest"] = "{:.2f}".format(
            float((interest["rebait_interest"]))
        )
        interest["base_interest"] = "{:.2f}".format(float((interest["base_interest"])))
    response = {"lender_data": lender_data, "interest_config": interest_config}
    return utils.respondWithSuccess(data=response)
