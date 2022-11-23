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
        # email_regex = r"^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,}$"
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
        # import random
        # import string

        # counter = 1
        # cust_data = []
        # while counter <= 500:
        #     mob_no = str(random.randint(1000000000, 9999999999))
        #     first_name = "".join(random.choice(string.ascii_letters) for x in range(10))
        #     last_name = "".join(random.choice(string.ascii_letters) for x in range(10))
        #     email = first_name + mob_no[:5] + "@gmail.com"
        #     pan_no = "CEFPC3206R"
        #     dob = "04-08-2001"
        #     ckyc_no = "50088727998324"
        #     bank = "HDFC BANK"
        #     branch = "ROURKELA PANPOSH ROAD ORISSA"
        #     acc_no = "3621000042135"
        #     ifsc = "HDFC0000362"
        #     city = "RAURKELA"
        #     address = "CHOUDHURY COMPLEX PANPOSH ROAD ROURKELAROURKELAORISSA769004"
        #     account_holder_name = first_name
        #     acc_type = "Saving"

        #     cust_data.append(
        #         [
        #             first_name,
        #             last_name,
        #             mob_no,
        #             email,
        #             pan_no,
        #             dob,
        #             ckyc_no,
        #             bank,
        #             branch,
        #             acc_no,
        #             ifsc,
        #             city,
        #             address,
        #             account_holder_name,
        #             acc_type,
        #         ]
        #     )
        #     counter += 1
        # print(cust_data)
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
