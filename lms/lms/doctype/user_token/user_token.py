# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document

# from frappe.core.doctype.sms_settings.sms_settings import send_sms
import lms


class UserToken(Document):
    def after_insert(self):
        if self.token_type in [
            "OTP",
            "Pledge OTP",
            "Withdraw OTP",
            "Unpledge OTP",
            "Sell Collateral OTP",
        ]:

            # OTP on Email as per new Requiement on Dec 10, 2021
            if self.token_type in [
                "Pledge OTP",
                "Unpledge OTP",
            ]:
                doc = frappe.get_all(
                    "User KYC", filters={"user": frappe.session.user}, fields=["*"]
                )[0]
                doc["otp_info"] = {
                    "token_type": self.token_type.replace(" ", ""),
                    "token": self.token,
                }
                frappe.enqueue_doc(
                    "Notification",
                    "OTP for Spark Loans",
                    method="send",
                    doc=doc,
                )
            else:
                doc = frappe.get_all(
                    "User", filters={"username": self.entity}, fields=["*"]
                )[0]
                doc["otp_info"] = {
                    "token_type": self.token_type.replace(" ", ""),
                    "token": self.token,
                }
                frappe.enqueue_doc(
                    "Notification",
                    "Other OTP for Spark Loans",
                    method="send",
                    doc=doc,
                )

            # las_settings = frappe.get_single("LAS Settings")
            # app_hash_string = (las_settings.app_identification_hash_string,)
            # "Your {token_type} for LMS is {token}. Do not share your {token_type} with anyone.{app_hash_string}"
            expiry_in_minutes = lms.user_token_expiry_map.get(self.token_type, None)
            # mess = frappe._(
            #     """Dear Customer,
            #     Your {token_type} for Spark Loans is {token}. Do not share your {token_type} with anyone.{app_hash_string} Your OTP is valid for {expiry_in_minutes} minutes.
            #     -Spark Loans""").format(
            #     token_type=self.token_type.replace(" ",""),
            #     token=self.token,
            #     app_hash_string=app_hash_string,
            #     expiry_in_minutes=expiry_in_minutes,
            # )
            mess = frappe._(
                # "Dear Customer,\nYour {token_type} for Spark Loans is {token}. Do not share your {token_type} with anyone. Your OTP is valid for 10 minutes -Spark Loans"
                "Dear Customer,\nYour {token_type} for Spark Loans is {token}. Do not share your {token_type} with anyone. Your OTP is valid for 10 minutes -Spark Loans"
            ).format(
                token_type=self.token_type.replace(" ", ""),
                token=self.token,
                # expiry_in_minutes=expiry_in_minutes,
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=[self.entity], msg=mess)
        elif self.token_type == "Email Verification Token":
            doc = frappe.get_doc("User", self.entity).as_dict()
            doc["url"] = frappe.utils.get_url(
                "/api/method/lms.auth.verify_user?token={}&user={}".format(
                    self.token, self.entity
                )
            )
            frappe.enqueue_doc(
                "Notification",
                "User Email Verification",
                method="send",
                # now=True,
                doc=doc,
            )
        elif self.token_type == "Forgot Pin OTP":
            customer = frappe.get_all(
                "Loan Customer", filters={"user": self.entity}, fields=["*"]
            )[0]
            expiry_in_minutes = lms.user_token_expiry_map.get(self.token_type, None)

            if customer.choice_kyc:
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            else:
                doc = frappe.get_doc("User", self.entity).as_dict()

            user_doc = frappe.get_doc("User", self.entity).as_dict()
            user_doc["otp_info"] = {
                "token_type": self.token_type.replace(" ", ""),
                "token": self.token,
            }
            frappe.enqueue_doc(
                "Notification",
                "Other OTP for Spark Loans",
                method="send",
                doc=user_doc,
            )

            """changes as per latest email notification list-sent by vinayak - email verification final 2.0"""
            # mess = _(
            #     """<html><body><h3>Dear Customer,<h3><br>
            # Your {token_type} for Spark Loans is {token}. Do not share your {token_type} with anyone.<br>
            # Your OTP is valid for {expiry_in_minutes} minutes<br>
            # -Spark Loans</body></html>"""
            # ).format(
            #     token_type=doc.get("otp_info").get("token_type").replace(" ", ""),
            #     token=doc.get("otp_info").get("token"),
            #     expiry_in_minutes=doc.get("otp_info").get("expiry_in_minutes"),
            # )

            # frappe.enqueue(
            #     method=frappe.sendmail,
            #     recipients=[doc.email if doc.email else doc.user],
            #     sender=None,
            #     subject="Forgot Pin Notification",
            #     message=mess,
            # )
            msg = frappe._(
                # "Dear Customer,\nYour {token_type} for Spark Loans is {token}. Do not share your {token_type} with anyone. Your OTP is valid for 10 minutes. -Spark Loans"
                "Dear Customer,\nYour {token_type} for Spark Loans is {token}. Do not share your {token_type} with anyone. Your OTP is valid for 10 minutes -Spark Loans"
            ).format(
                token_type=self.token_type.replace(" ", ""),
                token=self.token,
                # expiry_in_minutes=expiry_in_minutes,
            )
            if msg:
                receiver_list = list(set([str(customer.phone), str(doc.mobile_number)]))
                from frappe.core.doctype.sms_settings.sms_settings import send_sms

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)


# putting these here for the logs
# will be removed afterwards
# uncomment the import on line 8 after removing this
def validate_receiver_nos(receiver_list):
    validated_receiver_list = []
    for d in receiver_list:
        # remove invalid character
        for x in [" ", "-", "(", ")"]:
            d = d.replace(x, "")

        validated_receiver_list.append(d)

    if not validated_receiver_list:
        frappe.throw(_("Please enter valid mobile nos"))

    return validated_receiver_list


def send_sms(receiver_list, msg, sender_name="", success_msg=True):

    import json

    from six import string_types

    if isinstance(receiver_list, string_types):
        receiver_list = json.loads(receiver_list)
        if not isinstance(receiver_list, list):
            receiver_list = [receiver_list]

    receiver_list = validate_receiver_nos(receiver_list)

    arg = {
        "receiver_list": receiver_list,
        "message": frappe.safe_decode(msg).encode("utf-8"),
        "success_msg": success_msg,
    }

    if frappe.db.get_value("SMS Settings", None, "sms_gateway_url"):
        send_via_gateway(arg)
    else:
        frappe.msgprint(_("Please Update SMS Settings"))


def send_via_gateway(arg):
    ss = frappe.get_doc("SMS Settings", "SMS Settings")
    headers = get_headers(ss)

    args = {ss.message_parameter: arg.get("message")}
    for d in ss.get("parameters"):
        if not d.header:
            args[d.parameter] = d.value

    success_list = []
    for d in arg.get("receiver_list"):
        args[ss.receiver_parameter] = d
        status = send_request(ss.sms_gateway_url, args, headers, ss.use_post)

        if 200 <= status < 300:
            success_list.append(d)

    if len(success_list) > 0:
        args.update(arg)
        create_sms_log(args, success_list)
        if arg.get("success_msg"):
            frappe.msgprint(
                frappe._("SMS sent to following numbers: {0}").format(
                    "\n" + "\n".join(success_list)
                )
            )


def get_headers(sms_settings=None):
    if not sms_settings:
        sms_settings = frappe.get_doc("SMS Settings", "SMS Settings")

    headers = {"Accept": "text/plain, text/html, */*"}
    for d in sms_settings.get("parameters"):
        if d.header == 1:
            headers.update({d.parameter: d.value})

    return headers


def send_request(gateway_url, params, headers=None, use_post=False):
    import requests

    if not headers:
        headers = get_headers()

    if use_post:
        response = requests.post(gateway_url, headers=headers, data=params)
    else:
        response = requests.get(gateway_url, headers=headers, params=params)
    # SMS LOG
    import json

    frappe.logger().info(params)
    params["sms"] = params["sms"].decode("ascii")
    log = {
        "url": gateway_url,
        "params": params,
        "response": response.json(),
    }
    import os

    sms_log_file = frappe.utils.get_files_path("sms_log.json")
    sms_log = None
    if os.path.exists(sms_log_file):
        with open(sms_log_file, "r") as f:
            sms_log = f.read()
        f.close()
    sms_log = json.loads(sms_log or "[]")
    sms_log.append(log)
    with open(sms_log_file, "w") as f:
        f.write(json.dumps(sms_log))
    f.close()
    # SMS LOG end
    response.raise_for_status()
    return response.status_code


# Create SMS Log
# =========================================================
def create_sms_log(args, sent_to):
    sl = frappe.new_doc("SMS Log")
    from frappe.utils import nowdate

    sl.sent_on = nowdate()
    sl.message = args["message"].decode("utf-8")
    sl.no_of_requested_sms = len(args["receiver_list"])
    sl.requested_numbers = "\n".join(args["receiver_list"])
    sl.no_of_sent_sms = len(sent_to)
    sl.sent_to = "\n".join(sent_to)
    sl.flags.ignore_permissions = True
    sl.save()
