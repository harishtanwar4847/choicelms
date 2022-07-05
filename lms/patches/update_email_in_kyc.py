from datetime import datetime

import frappe
import requests

import lms


def execute():
    try:
        frappe.reload_doc("Lms", "DocType", "User KYC")
        user_kyc = frappe.get_all("User KYC", fields=["*"])
        for kyc in user_kyc:
            try:
                if not kyc["email"]:
                    las_settings = frappe.get_single("LAS Settings")
                    params = {
                        "PANNum": kyc["pan_no"],
                        "dob": kyc["date_of_birth"],
                    }

                    headers = {
                        "businessUnit": las_settings.choice_business_unit,
                        "userId": las_settings.choice_user_id,
                        "investorId": las_settings.choice_investor_id,
                        "ticket": las_settings.choice_ticket,
                    }

                    res = requests.get(
                        las_settings.choice_pan_api, params=params, headers=headers
                    )

                    data = res.json()
                    if res.ok and not "errorCode" in data:

                        # frappe.db.sql("""
                        # update `tabUser KYC` set email = '{}' where name = '{}'
                        # """.format(data["emailId"],kyc["name"]))

                        # confirmed by vinayak
                        user_kyc_doc = frappe.get_doc("User KYC", kyc["name"])
                        user_kyc_doc.email = data["emailId"]
                        user_kyc_doc.save(ignore_permissions=True)
                    frappe.db.commit()
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback() + "\nkyc.user {}".format(kyc.user),
                    title="email in kyc inner",
                )
    except Exception:
        frappe.log_error(title="email in kyc")
