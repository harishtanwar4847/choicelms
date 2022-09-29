# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
import utils
from frappe.model.document import Document

import lms


class SparkOfflineCustomerLog(Document):
    def before_save(self):
        if (
            self.user_status == "Success"
            and self.customer_status == "Success"
            and self.ckyc_status == "Success"
            and self.bank_status == "Success"
        ):
            self.status = "Success"
        elif (
            self.user_status == "Failure"
            and self.customer_status == "Failure"
            and self.ckyc_status == "Failure"
            and self.bank_status == "Failure"
        ):
            self.status = "Failure"
        else:
            self.status = "Partial Success"


@frappe.whitelist()
def retry_process(doc):
    try:
        print("Document :", doc)
        print("Document detail :", doc["user_status"])
        if (
            doc["user_status"] == "Failure" and doc["customer_status"] == "Failure"
        ) or (doc["user_status"] == "Pending" and doc["customer_status"] == "Pending"):
            print("Inside if :", doc["user_status"])
            # validation for name
            reg = lms.regex_special_characters(
                search=doc["first_name"] + doc["last_name"]
            )
            email_regex = (
                r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
            )
            if reg:
                frappe.throw(
                    frappe._(
                        "Special Characters not allowed in First Name and Last Name."
                    )
                )
                doc["user_status"] = "Failure"
                doc["customer_status"] = "Failure"
                doc.save(ignore_permissions=True)
                frappe.db.commit()

            # Validation for Email

            elif re.search(email_regex, doc["email_id"]) is None or (
                len(doc["email_id"].split("@")) > 2
            ):
                frappe.throw(frappe._("Please enter valid email ID."))
                doc["user_status"] = "Failure"
                doc["customer_status"] = "Failure"
                doc.save(ignore_permissions=True)
                frappe.db.commit()

            # validation for mobile number
            elif len(doc["mobile"]) > 10:
                frappe.throw(frappe._("Please enter valid Mobile Number."))
                doc["user_status"] = "Failure"
                doc["customer_status"] = "Failure"
                doc.save(ignore_permissions=True)
                frappe.db.commit()

            else:
                user = lms.create_user(
                    doc["first_name"],
                    doc["last_name"],
                    doc["mobile"],
                    doc["email_id"],
                    tester=0,
                )
                customer = lms.create_customer(user)
                print("USER {} Customer {} :".format(user, customer))
                doc["user_status"] = "Success"
                doc["customer_status"] = "Success"
                doc.save(ignore_permissions=True)
                frappe.db.commit()

        if doc["ckyc_status"] == "Failure" or doc["ckyc_status"] == "Pending":
            lms.ckyc_offline(customer=customer, offline_customer=doc)
            print("CKYC IN SPARK Off:")

        return utils.respondWithSuccess(
            message="Process Successfully completed", data=doc.name
        )

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Spark Offline Customer Log"),
        )
