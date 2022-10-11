# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import base64
import json

import frappe
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document

import lms


class UserKYC(Document):
    def on_update(self):
        status = []
        check = 0
        print("akash")
        for i in self.bank_account:
            status.append(i.bank_status)
        if "Approved" in status:
            check = 1
        print("razorpay_contact_id", self.razorpay_contact_id)
        self.kyc_update_and_notify_customer(check)
        for i in self.bank_account:
            print("outside on_update if")
            if i.personalized_cheque:
                print("inside on_update if")
                self.offline_customer_bank_verification()

    def kyc_update_and_notify_customer(self, check):
        print("inside kyc")
        cust_name = frappe.db.get_value("Loan Customer", {"user": self.user}, "name")
        loan_customer = frappe.get_doc("Loan Customer", cust_name)
        doc = self.as_dict()
        if (
            self.notification_sent == 0
            and self.kyc_status in ["Approved", "Rejected"]
            and not loan_customer.offline_customer
        ):
            if self.kyc_status == "Approved":
                if not loan_customer.kyc_update and not loan_customer.choice_kyc:
                    loan_customer.kyc_update = 1
                    loan_customer.choice_kyc = self.name
                    loan_customer.save(ignore_permissions=True)
                    frappe.db.commit()
                frappe.enqueue_doc(
                    "Notification", "Ckyc Approved", method="send", doc=doc
                )
                msg = "Your KYC Request has been approved, please visit spark.loans to continue the further journey."
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", "Ckyc Approved", fields=["*"]
                )
            else:
                frappe.enqueue_doc(
                    "Notification", "Ckyc Rejected", method="send", doc=doc
                )
                msg = "Your KYC Request has been rejected due to mismatch in details. Please visit spark.loans in order to reapply."
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", "Ckyc Rejected", fields=["*"]
                )

            receiver_list = [str(loan_customer.phone)]
            if self.mob_num:
                receiver_list.append(str(self.mob_num))
            if self.choice_mob_no:
                receiver_list.append(str(self.choice_mob_no))

            receiver_list = list(set(receiver_list))
            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification, customer=loan_customer
            )
            self.notification_sent = 1
            self.save(ignore_permissions=True)
            frappe.db.commit()

        if check and not loan_customer.bank_update:
            loan_customer.bank_update = 1
            loan_customer.save(ignore_permissions=True)
            frappe.db.commit()

        for i in self.bank_account:
            if i.notification_sent == 0 and i.bank_status in ["Approved", "Rejected"]:
                if i.bank_status == "Approved":
                    msg = "Your Bank details request has been approved; please visit spark.loans to continue the further journey to avail loan."
                    frappe.enqueue_doc(
                        "Notification", "Bank Approved", method="send", doc=doc
                    )
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification", "Bank Approved", fields=["*"]
                    )
                    i.notification_sent = 1
                    i.save(ignore_permissions=True)
                    frappe.db.commit()

                elif i.bank_status == "Rejected":
                    msg = "Your Bank request has been rejected due to mismatch in the details; please visit spark.loans in order to reapply."
                    frappe.enqueue_doc(
                        "Notification", "Bank Rejected", method="send", doc=doc
                    )
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification", "Bank Rejected", fields=["*"]
                    )
                    i.notification_sent = 1
                    i.save(ignore_permissions=True)
                    frappe.db.commit()

                receiver_list = [str(loan_customer.phone)]
                if self.mob_num:
                    receiver_list.append(str(self.mob_num))
                if self.choice_mob_no:
                    receiver_list.append(str(self.choice_mob_no))

                receiver_list = list(set(receiver_list))
                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
                lms.send_spark_push_notification(
                    fcm_notification=fcm_notification, customer=loan_customer
                )

    def validate(self):
        for i, item in enumerate(
            sorted(self.bank_account, key=lambda item: item.is_default, reverse=True),
            start=1,
        ):
            item.idx = i

    def offline_customer_bank_verification(self):
        user = frappe.get_all("User", filters={"email": self.user})

        for i in self.bank_account:
            account_holder_name = i.account_holder_name
            ifsc = i.ifsc
            account_number = i.account_number
            branch = i.branch
            city = i.city
            account_type = i.account_type
            if i.personalized_cheque and not self.razorpay_contact_id:
                print("ghal")
                contact_id = lms.penny_call_create_contact(user[0].name)
                if contact_id == "failed":
                    frappe.throw("failed")
                elif (
                    contact_id
                    == "Penny Drop Create contact Error - Razorpay Key Secret Missing"
                ):
                    frappe.throw(
                        "Penny Drop Create contact Error - Razorpay Key Secret Missing"
                    )
                else:
                    self.razorpay_contact_id = contact_id
                    self.save(ignore_permissions=True)
                    frappe.db.commit()

                create_fund_acc = lms.call_penny_create_fund_account(
                    user[0].name, ifsc, account_number, account_holder_name
                )
                print("create_fund_acc", create_fund_acc["fa_id"])
                if create_fund_acc == "failed":
                    frappe.throw("failed")
                elif (
                    create_fund_acc
                    == "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                ):
                    frappe.throw(
                        "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                    )

            if (
                i.personalized_cheque
                and self.razorpay_contact_id
                and not i.razorpay_fund_account_id
            ):
                print("VALIDATION")
                create_fund_acc = lms.call_penny_create_fund_account(
                    user[0].name, ifsc, account_number, account_holder_name
                )
                if create_fund_acc == "failed":
                    frappe.throw("failed")
                elif (
                    create_fund_acc
                    == "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                ):
                    frappe.throw(
                        "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                    )

                else:
                    fund_acc_validation = lms.call_penny_create_fund_account_validation(
                        user[0].name,
                        create_fund_acc["fa_id"],
                        account_type,
                        branch,
                        city,
                    )
                    print("user", user[0].name)
                    print("fund_acc_validation", fund_acc_validation)
                    if fund_acc_validation == "failed":
                        frappe.throw("Failed")
                    # try:
                    #     # check Loan Customer
                    #     customer = frappe.get_all("Loan Customer", filters={"user": user[0].name}, fields=["*"],)
                    #     print("customer")
                    #     if not customer:
                    #         # return utils.respondNotFound(message=frappe._("Customer not found."))
                    #         raise lms.exceptions.NotFoundException(_("Customer not found"))

            #             # fetch rzp key secret from las settings and use Basic auth
            #             las_settings = frappe.get_single("LAS Settings")
            #             if not las_settings.razorpay_key_secret:
            #                 frappe.log_error(
            #                     title="Penny Drop Fund Account Validation Error",
            #                     message="Penny Drop Fund Account Validation Error - Razorpay Key Secret Missing",
            #                 )
            #                 # return utils.respondWithFailure()
            #                 raise lms.exceptions.RespondWithFailureException()

            #             if not las_settings.razorpay_bank_account:
            #                 frappe.log_error(
            #                     title="Penny Drop Fund Account Validation Error",
            #                     message="Penny Drop Fund Account Validation Error - Razorpay Bank Account Missing",
            #                 )
            #                 # return utils.respondWithFailure()
            #                 raise lms.exceptions.RespondWithFailureException()

            #             razorpay_key_secret_auth = "Basic " + base64.b64encode(
            #                 bytes(las_settings.razorpay_key_secret, "utf-8")
            #             ).decode("ascii")

            #             try:
            #                 data_rzp = {
            #                     "account_number": las_settings.razorpay_bank_account,
            #                     "fund_account": data_resp,
            #                     "amount": 100,
            #                     "currency": "INR",
            #                     "notes": {
            #                         "branch": branch,
            #                         "city": city,
            #                         "bank_account_type": account_type,
            #                     },
            #                 }
            #                 url = las_settings.pennydrop_create_fund_account_validation
            #                 headers = {
            #                     "Authorization": razorpay_key_secret_auth,
            #                     "content-type": "application/json",
            #                 }
            #                 raw_res = requests.post(
            #                     url=url,
            #                     headers=headers,
            #                     data=json.dumps(data_rzp),
            #                 )
            #                 print("raw_res",raw_res)
            #                 data_res = raw_res.json()
            #                 log = {
            #                     "url": las_settings.pennydrop_create_fund_account_validation,
            #                     "headers": headers,
            #                     "request": data_rzp,
            #                     "response": data_res,
            #                 }
            #                 print("data_res",data_res)
            #                 lms.create_log(log, "rzp_pennydrop_create_fund_account_validation")
            #                 user_kyc = self.as_dict()
            #                 abc = lms.penny_api_response_handle(
            #                     data,
            #                     user_kyc,
            #                     customer,
            #                     data_res,
            #                     personalized_cheque=data,
            #                 )
            #                 if data_res.get("error"):
            #                     frappe.throw("Error")
            #             except requests.RequestException as e:
            #                 raise utils.exceptions.APIException(str(e))

            #         except utils.exceptions.APIException as e:
            #             lms.log_api_error()
            #             frappe.log_error(
            #                 title="Penny Drop Create fund account validation Error",
            #                 message=frappe.get_traceback()
            #                 + "\n\nPenny Drop Create fund account validation Error: "
            #                 + str(e.args),
            #             )

    # def penny_call_create_contact(self,user = None,customer = None ,user_kyc = None):
    #     try:
    #         # check Loan Customer
    #         # if not customer:
    #         customer = frappe.get_all("Loan Customer", filters={"user": user}, fields=["*"])

    #         if not customer:
    #                 # return utils.respondNotFound(message=frappe._("Customer not found."))
    #             raise lms.exceptions.NotFoundException(_("Customer not found"))

    #         # fetch rzp key secret from las settings and use Basic auth
    #         las_settings = frappe.get_single("LAS Settings")
    #         if not las_settings.razorpay_key_secret:
    #             frappe.log_error(
    #                 title="Penny Drop Create contact Error",
    #                 message="Penny Drop Create contact Error - Razorpay Key Secret Missing",
    #             )
    #             # return utils.respondWithFailure()
    #             raise lms.exceptions.FailureException(
    #                 _("Penny Drop Create contact Error - Razorpay Key Secret Missing")
    #             )

    #         razorpay_key_secret_auth = "Basic " + base64.b64encode(
    #         bytes(las_settings.razorpay_key_secret, "utf-8")
    #         ).decode("ascii")
    #         try:
    #             data_rzp = {
    #                 "name": customer[0].full_name,
    #                 "email": customer[0].user,
    #                 "contact": customer[0].phone,
    #                 "type": "customer",
    #                 "reference_id": customer[0].name,
    #                 "notes": {},
    #             }
    #             raw_res = requests.post(
    #                 las_settings.pennydrop_create_contact,
    #                 headers={
    #                     "Authorization": razorpay_key_secret_auth,
    #                     "content-type": "application/json",
    #                 },
    #                 data=json.dumps(data_rzp),
    #             )
    #             data_res = raw_res.json()

    #             if data_res.get("error"):
    #                 log = {
    #                     "request": data_rzp,
    #                     "response": data_res.get("error"),
    #                 }
    #                 lms.create_log(log, "rzp_penny_contact_error_log")
    #                 # return utils.respondWithFailure(message=frappe._("failed"))
    #                 raise lms.exceptions.RespondWithFailureException(_("failed"))

    #             # User KYC save
    #             """since CKYC development not done yet, using existing user kyc to update contact ID"""

    #             # update contact ID
    #             self.razorpay_contact_id = data_res.get("id")
    #             self.save(ignore_permissions=True)
    #             frappe.db.commit()

    #             lms.create_log(data_res, "rzp_penny_contact_success_log")
    #             # return utils.respondWithSuccess(message=frappe._("success"))

    #         except requests.RequestException as e:
    #             raise utils.exceptions.APIException(str(e))

    #     except utils.exceptions.APIException as e:
    #         lms.log_api_error()
    #         frappe.log_error(
    #             title="Penny Drop Create contact Error From backend",
    #             message=frappe.get_traceback()
    #             + "\n\nPenny Drop Create contact Error From backend: "
    #             + str(e.args),
    #         )
