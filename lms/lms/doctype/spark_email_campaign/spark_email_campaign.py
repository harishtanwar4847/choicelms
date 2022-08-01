# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta

# import frappe
from unicodedata import name

import frappe
from frappe.model.document import Document

import lms


class SparkEmailCampaign(Document):
    def on_submit(self):
        self.mail_send()

    def validate(self):
        if len(self.sender_email) > 1:
            frappe.throw(("Maximum 1 level allowed."))

    # def on_cancel(self):
    #     print("abcd")
    #     if self.schedule_time == "Immediate":
    #         frappe.throw("Immediate mails cannot be cancelled")

    #     scheduled_mails_cancel = frappe.get_all("Email Queue",filters={"send_after":self.schedule_datetime},fields = ["*"])
    #     print(len(scheduled_mails_cancel))
    #     if self.customer_selection == "Selected Customer":
    #         for i in self.customer_email:
    #             print(i.email_id)
    #     # doc = frappe.get_all("Loan Customer",filters={"send_after":self.self.customer_selection},fields=["user"])
    #     # for i in

    def before_save(self):
        for i in self.sender_email:
            if "spark" in i.email_id or "choice" in i.email_id:
                i.email_id
            else:
                frappe.throw("Please Enter Spark/Choice email id")

    def mail_send(self):
        doc_list = []
        if self.customer_selection == "All Customer":
            doc = frappe.get_all("Loan Customer", fields=["user"])
            for i in doc:
                doc_list.append(i.user)
        elif self.customer_selection == "Loan Customer":
            doc = frappe.get_all(
                "Loan Customer", filters={"loan_open": 1}, fields=["user"]
            )
            for i in doc:
                doc_list.append(i.user)
        elif self.customer_selection == "":
            doc = frappe.get_all("Loan Customer", fields=["user"])
            for i in doc:
                doc_list.append(i.user)
        elif self.customer_selection == "":
            doc = frappe.get_all("Loan Customer", fields=["user"])
            for i in doc:
                doc_list.append(i.user)
        else:
            for i in self.customer_email:
                doc_list.append(i.user)

        for i in self.sender_email:
            if "spark" in i.email_id or "choice" in i.email_id:
                sender = i.email_id

        for user in doc_list:
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=user,
                sender=sender,
                subject=self.subject,
                message=self.template_html,
                send_after=self.schedule_datetime,
            )
