# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class TopupApplication(Document):
    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def on_update(self):
        loan = frappe.get_doc("Loan", self.loan)
        if self.status == "Approved":
            loan.drawing_power += self.top_up_amount
            loan.sanctioned_limit += self.top_up_amount
            loan.save(ignore_permissions=True)

    #     self.notify_customer()

    # def notify_customer(self):
    #     from frappe.core.doctype.sms_settings.sms_settings import send_sms
    #     customer = self.get_customer()
    #     user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
    #     doc = frappe.get_doc("User", customer.user).as_dict()
    #     doc["top_up_application"] = {
    #         "status": self.status,
    #         "loan": self.loan,
    #         "top_up_amount": self.top_up_amount,
    #     }
    #     frappe.enqueue_doc("Notification", "Top up Application", method="send", doc=doc)

    #     if doc.get("top_up_application").get("status") == "Pending":
    #         mess = "Your request has been successfully received. You will be notified when your new OD limit is approved by our banking partner."
    #         frappe.enqueue(method=send_sms, receiver_list=list(set([str(customer.phone), str(user_kyc.mobile_number)])), msg=mess)

    #     if doc.get("top_up_application").get("status") == "Approved":
    #         mess = "Congratulations! Your Top up application for Loan {loan_name} is Approved.".format(doc.get("top_up_application").get("loan_name"))
    #         frappe.enqueue(method=send_sms, receiver_list=list(set([str(customer.phone), str(user_kyc.mobile_number)])), msg=mess)

    #     if doc.get("top_up_application").get("status") == "Rejected":
    #         mess = "Sorry! Your Top up application was turned down. We regret the inconvenience caused."
    #         frappe.enqueue(method=send_sms, receiver_list=list(set([str(customer.phone), str(user_kyc.mobile_number)])), msg=mess)

    # receiver_list = list(set([str(customer.phone), str(user_kyc.mobile_number)]))
