# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import timedelta

import frappe
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document

import lms


class UserKYC(Document):
    def on_update(self):
        status = []
        check = 0
        for i in self.bank_account:
            status.append(i.bank_status)
        if "Approved" in status:
            check = 1

        self.kyc_update_and_notify_customer(check)

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
            loan_renewal_doc.updated_kyc_status = self.kyc_status
            loan_renewal_doc.save(ignore_permissions=True)
            frappe.db.commit()
        if self.notification_sent == 0 and self.kyc_status in ["Approved", "Rejected"]:
            if self.updated_kyc == 1:
                if renewal_list:
                    if self.kyc_status == "Approved":
                        loan_renewal_doc.new_kyc_name = self.name
                        loan_renewal_doc.updated_kyc_status = self.kyc_status
                        loan_renewal_doc.save(ignore_permissions=True)
                        loan_customer.choice_kyc = self.name
                        loan_customer.save(ignore_permissions=True)
                        frappe.db.commit()

                        frappe.enqueue_doc(
                            "Notification", "CKYC Approved", method="send", doc=doc
                        )
                        msg = "Your KYC Request has been approved, please visit spark.loans to continue the further journey."
                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification", "Ckyc Approved", fields=["*"]
                        )
                    else:
                        loan_renewal_doc.updated_kyc_status = self.kyc_status
                        loan_renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()
                        frappe.enqueue_doc(
                            "Notification", "CKYC Rejected", method="send", doc=doc
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
                    msg = "Your KYC Request has been approved, please visit the spark.loans app to continue the further journey to avail loan. - {} -Spark Loans".format(
                        las_settings.app_login_dashboard
                    )
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification", "Ckyc Approved", fields=["*"]
                    )
                else:
                    frappe.enqueue_doc(
                        "Notification", "Ckyc Rejected", method="send", doc=doc
                    )
                    msg = "Your KYC Request has been rejected due to mismatch in details.  Please visit the spark.loans app to continue the further journey to avail loan. - {} -Spark Loans".format(
                        las_settings.app_login_dashboard
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
                    if i.notification_sent == 0 and i.bank_status in [
                        "Approved",
                        "Rejected",
                    ]:
                        if i.bank_status == "Approved":
                            msg = "Your Bank details request has been approved; please visit the spark.loans app to continue the further journey to avail loan. - {} -Spark Loans".format(
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
                            msg = "Your Bank request has been rejected due to mismatch in the details;  please visit the spark.loans app to continue the further journey to avail loan. - {} -Spark Loans".format(
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
                        frappe.enqueue(
                            method=send_sms, receiver_list=receiver_list, msg=msg
                        )
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
        cust_name = frappe.db.get_value("Loan Customer", {"user": self.user}, "name")
        customer = frappe.get_doc("Loan Customer", cust_name)
        loan_name = frappe.db.get_value("Loan", {"customer": cust_name}, "name")
        loan = frappe.get_doc("Loan", loan_name)
        date_7after_expiry = loan.expiry_date + timedelta(days=7)
        if (
            self.updated_kyc == 1
            and self.kyc_status == "Rejected"
            and self.creation > date_7after_expiry
        ):
            renewal_list = frappe.get_all(
                "Spark Loan Renewal Application",
                filters={"loan": loan_name, "status": "Pending"},
                fields=["*"],
            )
            renewal_doc = frappe.get_doc(
                "Spark Loan Renewal Application", renewal_list[0].name
            )

            renewal_doc.status = "Rejected"
            renewal_doc.workflowstate = "Rejected"
            renewal_doc.remarks = "KYC Rejected"
            renewal_doc.save(ignore_permissions=True)
            frappe.db.commit()
