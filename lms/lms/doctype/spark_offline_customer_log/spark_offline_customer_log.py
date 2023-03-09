# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
import utils
from frappe.model.document import Document

import lms


class SparkOfflineCustomerLog(Document):
    def before_save(self):
        # validations
        if self.first_name != self.customer_first_name:
            frappe.throw(
                "Users first name and Loan customers first name should be same"
            )

        if self.last_name != self.customer_last_name:
            frappe.throw("Users last name and Loan customers last name should be same")

        if self.mobile_no != self.customer_mobile:
            frappe.throw(
                "Users mobile number and Loan customers mobile number should be same"
            )

        if self.email_id != self.customer_email:
            frappe.throw("Users email and Loan customers email should be same")

        if self.ckyc_status == "Success":
            self.ckyc_remarks = ""
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
def retry_process(doc_name):
    try:
        doc = frappe.get_doc("Spark Offline Customer Log", doc_name)
        message = ""
        if (doc.user_status == "Failure" and doc.customer_status == "Failure") or (
            doc.user_status == "Pending" and doc.customer_status == "Pending"
        ):
            # validation for name
            reg = lms.regex_special_characters(
                search=doc.first_name
                + doc.last_name
                + doc.customer_first_name
                + doc.customer_last_name
            )
            email_regex = (
                r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
            )
            first_name = False
            last_name = False
            if " " in doc.first_name:
                first_name = True
                message += "Space not allowed user First Name.\n"
            if " " in doc.last_name:
                last_name = True
                message += "Space not allowed user Last Name.\n"
            if " " in doc.customer_first_name:
                first_name = True
                message += "Space not allowed customer First Name.\n"
            if " " in doc.customer_last_name:
                last_name = True
                message += "Space not allowed customer Last Name.\n"
            if reg:
                message += (
                    "Special Characters not allowed in First Name and Last Name.\n"
                )

            # Validation for Email
            if (re.search(email_regex, doc.email_id)) is None or (
                len(doc.email_id.split("@")) > 2
            ):
                message += "Please enter valid email ID.\n"

            if (re.search(email_regex, doc.customer_email)) is None or (
                len(doc.email_id.split("@")) > 2
            ):
                message += "Please enter customer valid email ID.\n"

            # validation for mobile number
            if (len(doc.mobile_no) != 10) or (doc.mobile_no.isnumeric() == False):
                message += "Please enter valid Mobile Number.\n"

            if (len(doc.customer_mobile) != 10) or (
                doc.customer_mobile.isnumeric() == False
            ):
                message += "Please enter valid customer Mobile Number.\n"

            # if doc.city.isalpha() == False:
            #     message += "Please enter valid city name.\n"

            if (
                (reg)
                or (
                    (re.search(email_regex, doc.email_id)) is None
                    or (len(doc.email_id.split("@")) > 2)
                )
                or (
                    (re.search(email_regex, doc.customer_email)) is None
                    or (len(doc.customer_email.split("@")) > 2)
                )
                or (
                    (len(doc.customer_mobile) != 10)
                    or (doc.customer_mobile.isnumeric() == False)
                )
                or (first_name)
                or (last_name)
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
                customer.mycams_email_id = doc.mycams_email_id
                doc.user_status = "Success"
                doc.customer_status = "Success"
                doc.user_remarks = message
                # doc.user_name = user.name
                doc.customer_name = customer.name
                customer.offline_customer = 1
                customer.is_email_verified = 1
                customer.save(ignore_permissions=True)
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
            if doc.customer_status == "Success":
                customer = frappe.get_doc("Loan Customer", cust_name)
                lms.ckyc_offline(customer=customer, offline_customer=doc)

        return utils.respondWithSuccess(
            message="Process Successfully completed", data=doc.name
        )

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback() + "\n\n Doc name = {}".format(str(doc_name)),
            title=frappe._("Spark Offline Customer Log"),
        )
