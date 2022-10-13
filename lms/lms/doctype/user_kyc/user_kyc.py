# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import base64
import json
from warnings import filters

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
                contact_id = lms.penny_call_create_contact(user[0].name)
                if contact_id == "failed":
                    frappe.throw("failed")
                elif contact_id.get("message") == "User not found":
                    frappe.throw("User not found")

                elif contact_id.get("message") == "Customer not found":
                    frappe.throw("Customer not found")

                elif (
                    contact_id.get("message")
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
                if create_fund_acc.get("message") == "failed":
                    frappe.throw("failed")

                elif create_fund_acc.get("message") == "Special Characters not allowed":
                    frappe.throw("Special Characters not allowed")

                elif create_fund_acc.get("message") == "User not found":
                    frappe.throw("User not found")

                elif (
                    create_fund_acc.get("message")
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
                create_fund_acc = lms.call_penny_create_fund_account(
                    user[0].name, ifsc, account_number, account_holder_name
                )
                if create_fund_acc.get("message") == "failed":
                    frappe.throw("failed")

                elif create_fund_acc.get("message") == "Special Characters not allowed":
                    frappe.throw("Special Characters not allowed")

                elif create_fund_acc.get("message") == "User not found":
                    frappe.throw("User not found")

                elif (
                    create_fund_acc.get("message")
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
                    print("fund_acc_validation", fund_acc_validation)
                    if fund_acc_validation.get("message") == "failed":
                        frappe.throw("Failed")

                    # elif (fund_acc_validation == "waiting for response from bank"):
                    #     frappe.throw("waiting for response from bank")

                    elif (
                        fund_acc_validation.get("message")
                        == "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                    ):
                        frappe.throw(
                            "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                        )

                    elif (
                        fund_acc_validation.get("message")
                        == "Penny Drop Fund Account Validation Error - Razorpay Bank Account Missing"
                    ):
                        frappe.throw(
                            "Penny Drop Fund Account Validation Error - Razorpay Bank Account Missing"
                        )

                    elif (
                        fund_acc_validation.get("message")
                        == "We have found a mismatch in the account holder name as per the fetched data"
                    ):
                        frappe.throw(
                            "We have found a mismatch in the account holder name as per the fetched data"
                        )

                    elif (
                        fund_acc_validation.get("message")
                        == "Your account details have not been successfully verified"
                    ):
                        frappe.throw(
                            "Your account details have not been successfully verified"
                        )

                    else:
                        if fund_acc_validation.get("status") == "completed":
                            print("inside else of userk kyc")
                            # For non choice user
                            i.razorpay_fund_account_id = fund_acc_validation.get(
                                "fund_account"
                            ).get("id")
                            i.razorpay_fund_account_validation_id = (
                                fund_acc_validation.get("id")
                            )
                            i.bank_status = "Pending"
                            i.save(ignore_permissions=True)
                            frappe.db.commit()
                            offline_cust = frappe.get_all(
                                "Spark Offline Customer Log",
                                filters={
                                    "ckyc_status": "Success",
                                    "email_id": user[0].name,
                                },
                                fields=["name"],
                            )
                            doc = frappe.get_doc(
                                "Spark Offline Customer Log", offline_cust[0].name
                            )
                            doc.bank_status = "Success"
                            doc.save(ignore_permissions=True)
                            frappe.db.commit()

                        else:
                            validation_by_id = (
                                lms.call_penny_create_fund_account_validation_by_id(
                                    user=user[0].name,
                                    fav_id="fav_JpGHajHOy3CNKb",
                                    personalized_cheque="abcd",
                                )
                            )
                            print("validation_by_id", validation_by_id)
                            if validation_by_id == "failed":
                                frappe.throw("Failed")

                            elif (
                                fund_acc_validation.get("message")
                                == "waiting for response from bank"
                            ):
                                frappe.throw("waiting for response from bank")

                            elif (
                                fund_acc_validation.get("message")
                                == "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                            ):
                                frappe.throw(
                                    "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
                                )

                            elif (
                                validation_by_id.get("message")
                                == "We have found a mismatch in the account holder name as per the fetched data"
                            ):
                                frappe.throw(
                                    "We have found a mismatch in the account holder name as per the fetched data"
                                )

                            elif (
                                validation_by_id.get("message")
                                == "Your account details have not been successfully verified"
                            ):
                                frappe.throw(
                                    "Your account details have not been successfully verified"
                                )

                            else:
                                print("inside else of userk kyc")
                                # For non choice user
                                i.razorpay_fund_account_id = validation_by_id.get(
                                    "fund_account"
                                ).get("id")
                                i.razorpay_fund_account_validation_id = (
                                    validation_by_id.get("id")
                                )
                                i.bank_status = "Pending"
                                i.save(ignore_permissions=True)
                                frappe.db.commit()
                                offline_cust = frappe.get_all(
                                    "Spark Offline Customer Log",
                                    filters={
                                        "ckyc_status": "Success",
                                        "email_id": user[0].name,
                                    },
                                    fields=["name"],
                                )
                                print("offline_cust", offline_cust)
                                doc = frappe.get_doc(
                                    "Spark Offline Customer Log", offline_cust[0].name
                                )
                                doc.bank_status = "Success"
                                doc.save(ignore_permissions=True)
                                frappe.db.commit()
