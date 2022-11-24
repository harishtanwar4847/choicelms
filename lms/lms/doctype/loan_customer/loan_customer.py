# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
import re

import frappe
import pandas as pd
from frappe import _
from frappe.model.document import Document

import lms
from lms.firebase import FirebaseAdmin


class LoanCustomer(Document):
    def before_insert(self):
        user = frappe.get_doc("User", self.user)

        self.first_name = user.first_name
        self.middle_name = user.middle_name
        self.last_name = user.last_name
        self.full_name = user.full_name
        # self.email = user.email
        self.phone = user.phone
        # self.user = user.phone
        self.user = user.email
        self.registeration = 1

    def get_kyc(self):
        return frappe.get_doc("User KYC", self.choice_kyc)

    def on_update(self):
        user_kyc = ""
        if self.choice_kyc:
            user_kyc = self.get_kyc().as_json()

        try:
            fa = FirebaseAdmin()
            fa.send_data(
                data={
                    "customer": self.as_json(),
                    "user_kyc": user_kyc,
                },
                tokens=lms.get_firebase_tokens(self.user),
            )
            # fa.send_message(
            #     title="Customer and KYC details",
            #     body="Customer name: {}".format(self.full_name),
            #     data={"customer": self.as_json(), "user_kyc": user_kyc},
            #     tokens=lms.get_firebase_tokens(self.user),
            # )
        except Exception:
            pass
        finally:
            fa.delete_app()

    def validate(self):
        email_regex = (
            r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
        )
        if self.mycams_email_id:
            if re.search(email_regex, self.mycams_email_id) is None or (
                len(self.mycams_email_id.split("@")) > 2
            ):
                frappe.throw("Please enter a valid email id")

    def before_save(self):
        phone = frappe.get_all("Loan Customer", filters={"phone": self.phone})
        if self.registeration == 0:
            if phone:
                frappe.throw(_("Mobile Number {} already exists".format(self.phone)))
            user = frappe.get_all("Loan Customer", filters={"user": self.user})
            if user:
                frappe.throw(_("User {} already exists".format(self.user)))


@frappe.whitelist()
def loan_customer_template():
    try:
        data = []
        df = pd.DataFrame(
            data,
            columns=[
                "First Name",
                "Last Name",
                "Mobile Number",
                "Email id",
                "Pan No",
                "DOB (dd-mm-yyyy)",
                "CKYC No",
                "Bank",
                "Branch",
                "Account No",
                "IFSC",
                "City",
                "Account Holder Name",
                "Bank Address",
                "Account Type",
            ],
        )
        file_name = "Customer_Details_{}".format(frappe.utils.now_datetime())
        sheet_name = "Customer Details"
        return lms.download_file(
            dataframe=df,
            file_name=file_name,
            file_extention="xlsx",
            sheet_name=sheet_name,
        )
    except Exception as e:
        lms.log_api_error(e)
