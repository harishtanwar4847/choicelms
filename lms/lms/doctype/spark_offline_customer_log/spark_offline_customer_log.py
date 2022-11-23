# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
import utils
from frappe.model.document import Document

import lms


class SparkOfflineCustomerLog(Document):
    def before_save(self):
        print("ABCFGShgsv")
        if self.ckyc_status == "Success":
            self.ckyc_remarks = ""
            # self.save(ignore_permissions=True)
            # frappe.db.commit()
        if (
            self.user_status == "Success"
            and self.customer_status == "Success"
            and self.ckyc_status == "Success"
            and self.bank_status == "Success"
        ):
            self.user_remarks = ""
            self.customer_remarks = ""
            self.ckyc_remarks = ""
            self.bank_remarks = ""
            self.status = "Success"
            # self.save(ignore_permissions=True)
            # frappe.db.commit()
        elif (
            self.user_status == "Failure"
            and self.customer_status == "Failure"
            and self.ckyc_status == "Failure"
            and self.bank_status == "Failure"
        ):
            self.status = "Failure"
            # self.save(ignore_permissions=True)
            # frappe.db.commit()
        else:
            self.status = "Partial Success"
            # self.save(ignore_permissions=True)
            # frappe.db.commit()


@frappe.whitelist()
def retry_process(doc_name):
    try:
        doc = frappe.get_doc("Spark Offline Customer Log", doc_name)
        message = ""
        if (doc.user_status == "Failure" and doc.customer_status == "Failure") or (
            doc.user_status == "Pending" and doc.customer_status == "Pending"
        ):
            # validation for name
            reg = lms.regex_special_characters(search=doc.first_name + doc.last_name)
            email_regex = (
                r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
            )
            if reg:
                message += (
                    "Special Characters not allowed in First Name and Last Name.\n"
                )

            # Validation for Email
            if (re.search(email_regex, doc.email_id)) is None or (
                len(doc.email_id.split("@")) > 2
            ):
                message += "Please enter valid email ID.\n"

            # validation for mobile number
            if (len(doc.mobile_no) != 10) or (doc.mobile_no.isnumeric() == False):
                print("zkjvzlkj")
                message += "Please enter valid Mobile Number.\n"

            if doc.city.isaplha() == False:
                message += "Please enter valid city name.\n"

            if (
                (reg)
                or (
                    (re.search(email_regex, doc.email_id)) is None
                    or (len(doc.email_id.split("@")) > 2)
                )
                or ((len(doc.mobile_no) != 10) or (doc.mobile_no.isnumeric() == False))
            ):
                doc.user_status = "Failure"
                doc.customer_status = "Failure"
                doc.user_remarks = message
                doc.save(ignore_permissions=True)
                frappe.db.commit()

            else:
                user = lms.create_user(
                    doc.first_name,
                    doc.last_name,
                    doc.mobile_no,
                    doc.email_id,
                    tester=0,
                )
                customer = lms.create_customer(user)
                doc.user_status = "Success"
                doc.customer_status = "Success"
                doc.user_remarks = message
                doc.save(ignore_permissions=True)
                frappe.db.commit()

        # Pan and IFSC code regex
        message = ""
        alphanum_regex = "^(?=.*[a-zA-Z])(?=.*[0-9])[A-Za-z0-9]+$"
        pan_regex = "[A-Za-z]{5}[0-9]{4}[A-Za-z]{1}"
        if (re.search(pan_regex, doc.pan_no) is None) or (
            re.search(alphanum_regex, doc.ifsc) is None
        ):
            message += "Please enter valid Pan No or IFSC code.\n"

        # Validation for CKYC number and IFSC code
        if (doc.ckyc_no.isnumeric() == False) or (doc.account_no.isnumeric() == False):
            message += "Please enter valid CKYC Number or Account Number.\n"

        if (
            (
                (re.search(pan_regex, doc.pan_no) is None)
                or (re.search(alphanum_regex, doc.ifsc) is None)
            )
            or (doc.ckyc_no.isnumeric() == False)
            or (doc.account_no.isnumeric() == False)
        ):
            doc.ckyc_remarks = message
            doc.save(ignore_permissions=True)
            frappe.db.commit()

        elif doc.ckyc_status == "Failure" or doc.ckyc_status == "Pending":
            cust_name = frappe.get_value(
                "Loan Customer", {"phone": doc.mobile_no, "user": doc.email_id}, "name"
            )
            customer = frappe.get_doc("Loan Customer", cust_name)
            lms.ckyc_offline(customer=customer, offline_customer=doc)

        return utils.respondWithSuccess(
            message="Process Successfully completed", data=doc.name
        )

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Spark Offline Customer Log"),
        )
