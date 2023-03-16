# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import base64
import json
from datetime import datetime, time, timedelta
from warnings import filters

import frappe
import requests
import utils
from frappe import _
from frappe.model.document import Document

import lms
from lms.lms.doctype.user_token.user_token import send_sms


class UserKYC(Document):
    def before_save(self):
        if self.consent_given == 1:
            if self.kyc_status == "Approved":
                if self.address_details:
                    cust_add = frappe.get_doc(
                        "Customer Address Details", self.address_details
                    )
                    if not cust_add.perm_image:
                        frappe.throw("POA missing in address details doctype")
                    elif not cust_add.corres_poa_image:
                        frappe.throw("POA missing in address details doctype")

    def on_update(self):
        status = []
        check = 0
        for i in self.bank_account:
            status.append(i.bank_status)
        if "Approved" in status:
            check = 1
        self.kyc_update_and_notify_customer(check)
        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        user_role = []
        for i in list(user_roles):
            user_role.append(i[0])
        if "Loan Customer" not in user_role:
            self.offline_customer_bank_verification()

    def kyc_update_and_notify_customer(self, check):
        cust_name = frappe.db.get_value("Loan Customer", {"user": self.user}, "name")
        loan_customer = frappe.get_doc("Loan Customer", cust_name)
        doc = self.as_dict()
        las_settings = frappe.get_single("LAS Settings")
        renewal_list = frappe.db.get_value(
            "Spark Loan Renewal Application",
            {"customer": cust_name, "status": "Pending"},
            "name",
        )
        if renewal_list:
            loan_renewal_doc = frappe.get_doc(
                "Spark Loan Renewal Application", renewal_list
            )
            if self.consent_given == 1:
                kyc_status = self.kyc_status
            else:
                kyc_status = ""
            loan_renewal_doc.updated_kyc_status = kyc_status
            loan_renewal_doc.save(ignore_permissions=True)
            frappe.db.commit()
        if (
            self.notification_sent == 0
            and self.kyc_status in ["Approved", "Rejected"]
            and not loan_customer.offline_customer
        ):
            if self.updated_kyc == 1:
                if renewal_list:
                    if self.kyc_status == "Approved":
                        loan_renewal_doc.new_kyc_name = self.name
                        loan_renewal_doc.updated_kyc_status = self.kyc_status
                        loan_renewal_doc.kyc_approval_date = frappe.utils.now_datetime()
                        loan_renewal_doc.save(ignore_permissions=True)
                        loan_customer.choice_kyc = self.name
                        loan_customer.save(ignore_permissions=True)
                        frappe.db.commit()

                        frappe.enqueue_doc(
                            "Notification", "CKYC Approved", method="send", doc=doc
                        )
                        msg = "Your KYC Request has been approved, please visit the spark.loans app to continue the further journey to avail loan.- {link}\n-Spark Loans".format(
                            link=las_settings.app_login_dashboard
                        )
                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification", "Ckyc Approved", fields=["*"]
                        )
                    else:
                        print("Inside elseuuej")
                        if self.consent_given == 1:
                            kyc_status = self.kyc_status
                        else:
                            kyc_status = ""
                        loan_renewal_doc.updated_kyc_status = kyc_status
                        loan_renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()
                        frappe.enqueue_doc(
                            "Notification", "Ckyc Rejection", method="send", doc=doc
                        )
                        msg = "Your KYC Request has been rejected due to mismatch in details.  Please visit the spark.loans app to continue the further journey to avail loan. - {link}\n-Spark Loans".format(
                            link=las_settings.app_login_dashboard
                        )
                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification", "Ckyc Rejected", fields=["*"]
                        )

                    receiver_list = [str(loan_customer.phone)]
                    if self.mob_num:
                        receiver_list.append(str(self.mob_num))
                    if self.choice_mob_no:
                        receiver_list.append(str(self.choice_mob_no))

                    receiver_list = list(set(receiver_list))
                    frappe.enqueue(
                        method=send_sms, receiver_list=receiver_list, msg=msg
                    )
                    lms.send_spark_push_notification(
                        fcm_notification=fcm_notification, customer=loan_customer
                    )
                    self.notification_sent = 1
                    self.save(ignore_permissions=True)
                    frappe.db.commit()
                else:
                    return lms.exceptions.NotFoundException(
                        _("Loan Renewal Application not found")
                    )

            else:
                if self.kyc_status == "Approved":
                    if not loan_customer.kyc_update and not loan_customer.choice_kyc:
                        loan_customer.kyc_update = 1
                        loan_customer.choice_kyc = self.name
                        loan_customer.save(ignore_permissions=True)
                        frappe.db.commit()
                    frappe.enqueue_doc(
                        "Notification", "Ckyc Approved", method="send", doc=doc
                    )
                    msg = "Your KYC Request has been approved, please visit the spark.loans app to continue the further journey to avail loan. - {link} -Spark Loans".format(
                        link=las_settings.app_login_dashboard
                    )
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification", "Ckyc Approved", fields=["*"]
                    )
                else:
                    frappe.enqueue_doc(
                        "Notification", "Ckyc Rejection", method="send", doc=doc
                    )
                    msg = "Your KYC Request has been rejected due to mismatch in details. Please visit the spark.loans app to continue the further journey to avail loan. - {link} -Spark Loans".format(
                        link=las_settings.app_login_dashboard
                    )
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
            if (
                i.notification_sent == 0
                and i.bank_status in ["Approved", "Rejected"]
                and not loan_customer.offline_customer
            ):
                if i.bank_status == "Approved":
                    msg = "Your Bank details request has been approved, please visit the spark.loans app to continue the further journey to avail loan. - {} -Spark Loans".format(
                        las_settings.app_login_dashboard
                    )
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
                    msg = "Your Bank request has been rejected due to mismatch in the details. Please visit the spark.loans app to continue the further journey to avail loan. - {} -Spark Loans".format(
                        las_settings.app_login_dashboard
                    )
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

    def before_save(self):
        if self.consent_given == 1:
            if self.kyc_status == "Approved":
                if self.address_details:
                    cust_add = frappe.get_doc(
                        "Customer Address Details", self.address_details
                    )
                    if not cust_add.perm_image:
                        frappe.throw("POA missing in address details doctype")
                    elif not cust_add.corres_poa_image:
                        frappe.throw("POA missing in address details doctype")

        cust_name = frappe.db.get_value("Loan Customer", {"user": self.user}, "name")
        customer = frappe.get_doc("Loan Customer", cust_name)
        loan_name = frappe.db.get_value("Loan", {"customer": cust_name}, "name")
        if loan_name:
            loan = frappe.get_doc("Loan", loan_name)
            date_7after_expiry = loan.expiry_date + timedelta(days=7)
            if type(self.creation) == str:
                creation_date = datetime.strptime(
                    self.creation, "%Y-%m-%d %H:%M:%S.%f"
                ).date()
            else:
                creation_date = self.creation.date()
            if (
                self.updated_kyc == 1
                and self.kyc_status == "Rejected"
                and creation_date > date_7after_expiry
            ):
                renewal_list = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={"loan": loan_name, "status": "Pending"},
                    fields=["*"],
                )
                for doc in renewal_list:
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application", doc.name
                    )

                    renewal_doc.status = "Rejected"
                    renewal_doc.workflow_state = "Rejected"
                    renewal_doc.remarks = "KYC Rejected"
                    renewal_doc.save(ignore_permissions=True)
                    frappe.db.commit()

    def offline_customer_bank_verification(self):
        cust_name = frappe.db.get_value("Loan Customer", {"user": self.user}, "name")
        loan_customer = frappe.get_doc("Loan Customer", cust_name)
        user = frappe.get_all("User", filters={"email": self.user})
        las_settings = frappe.get_single("LAS Settings")
        for i in self.bank_account:
            if i.personalized_cheque and not i.penny_request_id:
                if self.kyc_status == "Approved":
                    data = {
                        "ifsc": i.ifsc,
                        "account_number": i.account_number,
                        "bank_account_type": i.account_type,
                        "bank": i.bank,
                        "branch": i.branch,
                        "city": i.city,
                    }
                    reg = lms.regex_special_characters(
                        search=data.get("ifsc")
                        + data.get("account_number")
                        + data.get("bank_account_type")
                        if data.get("bank_account_type")
                        else "" + data.get("bank")
                    )
                    if reg:
                        frappe.throw(_("Special Characters not allowed."))

                    res_json = lms.au_pennydrop_api(data, self.fullname)
                    if res_json:
                        if (
                            res_json.get("status_code") == 200
                            and res_json.get("message") == "Success"
                        ):
                            result_ = res_json.get("body").get("Result")
                            if res_json.get("body").get("status-code") == "101":
                                if result_.get("bankTxnStatus") == True:
                                    if not result_.get("accountName").lower():
                                        frappe.throw(
                                            "We have found a mismatch in the account holder name as per the fetched data"
                                        )

                                    else:
                                        matching = res_json.get("body").get(
                                            "fuzzy_match_score"
                                        )
                                        if (
                                            not matching
                                            or matching
                                            < las_settings.penny_name_mismatch_percentage
                                        ):
                                            # user_kyc = frappe.get_doc("User KYC", self.name)
                                            frappe.get_doc(
                                                {
                                                    "doctype": "Penny Name Mismatch",
                                                    "customer": loan_customer.name,
                                                    "user_kyc": self.name,
                                                    "kyc_first_name": self.fname,
                                                    "kyc_middle_name": self.mname,
                                                    "kyc_last_name": self.lname,
                                                    "kyc_full_name": self.fullname,
                                                    "penny_response_account_name": result_.get(
                                                        "accountName"
                                                    ),
                                                    "bank": data.get("bank"),
                                                    "branch": data.get("branch"),
                                                    "city": data.get("city"),
                                                    "penny_request_id": res_json.get(
                                                        "body"
                                                    ).get("request_id"),
                                                    "is_offline": True,
                                                    "ifsc": data.get("ifsc"),
                                                    "account_number": result_.get(
                                                        "accountNumber"
                                                    ),
                                                    "bank_transaction_status": result_.get(
                                                        "bankTxnStatus"
                                                    ),
                                                    "account_type": data.get(
                                                        "bank_account_type"
                                                    ),
                                                }
                                            ).insert()
                                            frappe.db.commit()
                                            frappe.throw(
                                                "We have found a mismatch in the account holder name as per the fetched data"
                                            )
                                        try:
                                            las_settings = frappe.get_single(
                                                "LAS Settings"
                                            )
                                            params = {
                                                "PANNum": self.pan_no,
                                                "dob": self.date_of_birth,
                                            }
                                            headers = {
                                                "businessUnit": las_settings.choice_business_unit,
                                                "userId": las_settings.choice_user_id,
                                                "investorId": las_settings.choice_investor_id,
                                                "ticket": las_settings.choice_ticket,
                                            }
                                            res_bank = requests.get(
                                                las_settings.choice_pan_api,
                                                params=params,
                                                headers=headers,
                                            )
                                            data_bank = res_bank.json()
                                            log = {
                                                "url": las_settings.choice_pan_api,
                                                "headers": headers,
                                                "request": params,
                                                "response": data,
                                            }
                                            lms.create_log(
                                                log,
                                                "offline_customer_get_bank_details_log",
                                            )
                                            if (
                                                res_bank.ok
                                                and "errorCode" not in data_bank
                                                and data_bank.get("banks")
                                            ):
                                                frappe.db.set_value(
                                                    "User KYC",
                                                    self.name,
                                                    {
                                                        "kyc_type": "CHOICE",
                                                        "email": data_bank["emailId"],
                                                        "choice_mob_no": data_bank[
                                                            "mobileNum"
                                                        ],
                                                    },
                                                )
                                        except Exception:
                                            frappe.throw("Get bank details not working")

                                        i.bank_status = "Pending"
                                        i.penny_request_id = res_json.get("body").get(
                                            "request_id"
                                        )
                                        i.account_holder_name = result_.get(
                                            "accountName"
                                        )
                                        i.bank_transaction_status = result_.get(
                                            "bankTxnStatus"
                                        )
                                        i.is_default = 1
                                        i.save()
                                        frappe.db.commit()
                                        self.reload()

                                        frappe.msgprint(
                                            "Your account details have been successfully verified"
                                        )
                                        offline_cust = frappe.get_all(
                                            "Spark Offline Customer Log",
                                            filters={
                                                "ckyc_status": "Success",
                                                "email_id": user[0].name,
                                            },
                                            fields=["name"],
                                        )
                                        if offline_cust:
                                            doc = frappe.get_doc(
                                                "Spark Offline Customer Log",
                                                offline_cust[0].name,
                                            )
                                            doc.bank_status = "Success"
                                            doc.save(ignore_permissions=True)
                                            frappe.db.commit()
                                else:
                                    lms.log_api_error(mess=str(res_json))
                                    frappe.throw(
                                        result_.get("bankResponse"),
                                    )
                            else:
                                lms.log_api_error(mess=str(res_json))
                                frappe.throw(
                                    "Your bank account details are not verified, please try again after sometime."
                                )
                        else:
                            lms.log_api_error(mess=str(res_json))
                            frappe.throw(
                                str(res_json.get("StatusCode"))
                                + "\n"
                                + str(res_json.get("Message"))
                            )
                else:
                    frappe.throw("Please approve User KYC")
