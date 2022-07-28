# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta

# import frappe
from unicodedata import name

import frappe
from frappe.model.document import Document

import lms


class EmailCampaign(Document):
    def on_submit(self):
        # self.cron_convertor()
        self.mail_send()

    # def add_new_cron_for_email(self,cron):
    # 	try:
    # 		print("abcd")
    # 		frappe.delete_doc("Scheduled Job Type", "lms.web_mail")
    # 		doc = frappe.get_doc(
    # 			{
    # 				"doctype": "Scheduled Job Type",
    # 				"method": "lms.web_mail",
    # 				"frequency": "Cron",
    # 				"cron_format": cron,
    # 				"last_execution" : frappe.utils.now_datetime() - timedelta(minutes = 5)
    # 			}
    # 		)
    # 		doc.insert(ignore_permissions=True)
    # 		print(doc.name)
    # 	except:
    # lms.log_api_error()

    # def cron_convertor(self):
    # 	print("time",(self.date_time_picker))
    # 	dt = self.date_time_picker
    # 	dt_obj = datetime.strptime(dt,'%Y-%m-%d %H:%M:%S')
    # 	print("dt",dt)
    # 	print("obj",type(dt_obj))
    # 	cron  = f"{dt_obj.minute} {dt_obj.hour} {dt_obj.day} {dt_obj.month} *"

    # 	print("Cron",cron)
    # 	self.add_new_cron_for_email(cron)
    # 	self.mail_send()

    def before_save(self):
        self.logo_file = frappe.utils.get_url("/assets/lms/mail_images/logo.png")
        self.fb_icon = frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png")
        self.tw_icon = frappe.utils.get_url("/assets/lms/mail_images/tw-icon.png")
        self.inst_icon = frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png")
        for i in self.sender:
            if "spark" in i.email_id or "choice" in i.email_id:
                i.email_id
            else:
                frappe.throw("Please Enter Spark/Choice email id")

    def mail_send(self):
        print(self.title)
        print(self.subject)
        print(self.customer_selection)
        # print(self.no_of_users)
        if self.customer_selection == "All Customer":
            doc = frappe.get_all("Loan Customer", fields=["user"])
        elif self.customer_selection == "Loan Customer":
            doc = frappe.get_all(
                "Loan Customer", filters={"loan_open": 1}, fields=["user"]
            )
        elif self.customer_selection == "":
            doc = frappe.get_all("Loan Customer", fields=["user"])
        elif self.customer_selection == "":
            doc = frappe.get_all("Loan Customer", fields=["user"])
        else:
            pass
        print(doc)
        print(len(doc))
        print(self.sender[0].email_id)
        for i in self.sender:
            if "spark" in i.email_id or "choice" in i.email_id:
                sender = i.email_id

        for i in doc:
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=i.user,
                sender=sender,
                subject=self.subject,
                message=self.html,
                send_after=self.datetime,
            )

    # def web_mail(notification_name, name, recepient, subject):
    # 	mail_content = frappe.db.sql(
    # 		"select message from `tabNotification` where name='{}';".format(
    # 			notification_name
    # 		)
    # 	)[0][0]
    # 	mail_content = mail_content.replace(
    # 		"user_name",
    # 		"{}".format(name),
    # 	)
    # 	mail_content = mail_content.replace(
    # 		"logo_file",
    # 		frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
    # 	)
    # 	mail_content = mail_content.replace(
    # 		"fb_icon",
    # 		frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
    # 	)
    # 	mail_content = mail_content.replace(
    # 		"tw_icon",
    # 		frappe.utils.get_url("/assets/lms/mail_images/tw-icon.png"),
    # 	)
    # 	mail_content = mail_content.replace(
    # 		"inst_icon",
    # 		frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
    # 	)
    # 	mail_content = (
    # 		mail_content.replace(
    # 			"lin_icon", frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png")
    # 		),
    # 	)
    # 	frappe.enqueue(
    # 		method=frappe.sendmail,
    # 		recipients=["{}".format(recepient)],
    # 		sender=None,
    # 		subject="{}".format(subject),
    # 		message=mail_content[0],
    # 	)


# @frappe.whitelist()
# def get_email_address():
#     doc = frappe.get_all(
#         "Email Account", fields = ["email_id"]
#     )
#     email_list = []
#     for i in doc:
#         if "spark" in i.email_id or "choice" in i.email_id :
#             email_list.append(i.email_id)
#     email_list.append("Other")
#     return email_list
