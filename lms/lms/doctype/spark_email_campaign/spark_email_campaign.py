# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta

# import frappe
from unicodedata import name

import frappe
from frappe.model.document import Document

import lms


class SparkEmailCampaign(Document):
    def validate(self):
        if len(self.sender_email) > 1:
            frappe.throw(frappe._("Maximum 1 level allowed."))
        if not len(self.sender_email):
            frappe.throw(frappe._("Please select at least one sender email account"))

        for i in self.sender_email:
            if not ("spark" in i.email_id or "choice" in i.email_id):
                frappe.throw(frappe._("Please Enter Spark/Choice email id"))

        if self.schedule_time == "Schedule":
            if self.schedule_datetime < frappe.utils.now_datetime().strftime(
                "%Y-%m-%d %H:%M:%S"
            ):
                frappe.throw("Scheduled time cannot be less than current time")

    def on_cancel(self):
        frappe.session.user = "Administrator"
        if self.schedule_time == "Immediate":
            frappe.throw("Immediate mails cannot be cancelled")
        final_list = []
        scheduled_mails_cancel = frappe.get_all(
            "Email Queue",
            filters={
                "send_after": self.schedule_datetime,
                "sender": self.sender_email[0].email_id,
                "status": "Not Sent",
            },
            pluck="name",
        )
        for i in scheduled_mails_cancel:
            recipient_doc = frappe.get_all(
                "Email Queue Recipient", filters={"parent": i}
            )
            if recipient_doc:
                final_list.append(i)

        frappe.delete_doc("Email Queue", final_list)

    def user_data(self):
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
        elif self.customer_selection == "Non Loan Customer":
            doc = frappe.get_all(
                "Loan Customer", fields=["user"], filters={"loan_open": 0}
            )
            for i in doc:
                doc_list.append(i.user)
        elif self.customer_selection == "Kyc Customer":
            doc = frappe.get_all(
                "Loan Customer", fields=["user"], filters={"kyc_update": 1}
            )
            for i in doc:
                doc_list.append(i.user)
        else:
            for i in self.customer_email:
                doc_list.append(i.user)

        return doc_list

    def before_save(self):
        customer_list = self.user_data()
        self.no_of_user = len(customer_list)
        self.logo_file = frappe.utils.get_url("/assets/lms/mail_images/logo.png")
        self.fb_icon = frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png")
        self.tw_icon = frappe.utils.get_url("/assets/lms/mail_images/tw-icon.png")
        self.inst_icon = frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png")
        if self.schedule_time == "Immediate":
            self.schedule_datetime = ""
        if self.customer_selection != "Selected Customer":
            self.customer_email = []

    def mail_send(self):
        customer_list = self.user_data()

        frappe.enqueue(
            method=frappe.sendmail,
            recipients=customer_list,
            sender=self.sender_email[0].email_id,
            subject=self.subject,
            message=self.template_html,
            send_after=self.schedule_datetime,
        )

    def on_submit(self):
        self.mail_send()
