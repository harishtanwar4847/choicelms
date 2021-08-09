# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import frappe
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
