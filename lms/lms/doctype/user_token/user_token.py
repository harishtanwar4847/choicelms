# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document

import lms


class UserToken(Document):
    def after_insert(self):
        las_settings = frappe.get_single("LAS Settings")
        if self.token_type in [
            "OTP",
            "Pledge OTP",
            "Withdraw OTP",
            "Unpledge OTP",
            "Sell Collateral OTP",
            "Lien OTP",
            "Invoke OTP",
            "Revoke OTP",
            "Loan Renewal OTP",
        ]:
            token_type = self.token_type.replace(" ", "")
            if self.token_type in [
                "Pledge OTP",
                "Unpledge OTP",
            ]:
                doc = frappe.get_all(
                    "User KYC", filters={"user": frappe.session.user}, fields=["*"]
                )[0]
                if doc:
                    email_otp = frappe.db.sql(
                        "select message from `tabNotification` where name='OTP for Spark Loans';"
                    )[0][0]
                    email_otp = email_otp.replace("investor_name", doc.fullname)
                    email_otp = email_otp.replace("token_type", token_type)
                    email_otp = email_otp.replace("token", self.token)
                    frappe.enqueue(
                        method=frappe.sendmail,
                        recipients=[doc.email],
                        sender=None,
                        subject="OTP for Spark Loans",
                        message=email_otp,
                        queue="short",
                        delayed=False,
                        job_name="Spark OTP on Email",
                    )
            else:
                doc = frappe.get_all(
                    "User", filters={"username": self.entity}, fields=["*"]
                )
                if doc:
                    # doc[0]["doctype"] = "User"
                    # doc[0]["otp_info"] = {
                    #     "token_type": self.token_type.replace(" ", ""),
                    #     "token": self.token,
                    # }
                    # frappe.enqueue_doc(
                    #     "Notification",
                    #     "Other OTP for Spark Loans",
                    #     method="send",
                    #     doc=doc[0],
                    # )
                    email_otp = frappe.db.sql(
                        "select message from `tabNotification` where name='Other OTP for Spark Loans';"
                    )[0][0]
                    email_otp = email_otp.replace("investor_name", doc[0].full_name)
                    email_otp = email_otp.replace("token_type", token_type)
                    email_otp = email_otp.replace("token", self.token)
                    if self.token_type != "Withdraw OTP":
                        frappe.enqueue(
                            method=frappe.sendmail,
                            recipients=[doc[0].email],
                            sender=None,
                            subject="OTP for Spark Loans",
                            message=email_otp,
                            queue="short",
                            delayed=False,
                            job_name="Spark OTP on Email",
                        )

            if self.token_type == "OTP":
                mess = """<#> Dear customer, your login OTP is {token}. Thank you for choosing Spark Loans. Do not share OTP for security reasons. Valid for 10 mins

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
            if self.token_type == "Pledge OTP":
                mess = """<#> Dear customer, use OTP {token} to securely Pledge your securities. DO NOT disclose it to anyone to keep your account safe. Valid for 10 mins

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
            if self.token_type == "Withdraw OTP":
                mess = """<#> Dear customer, use OTP {token} to complete your withdrawal transaction request. NEVER share your OTP with anyone. OTP Expires in 10 mins

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
                mess = ""
            if self.token_type == "Unpledge OTP":
                mess = """<#> Dear customer, use OTP {token} for un-pledging securities at Spark Loans. Keep it confidential and enter to complete the request. Valid for 10 mins

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
            if self.token_type == "Sell Collateral OTP":
                mess = """<#> Dear customer, use OTP {token} to complete your sell securities request with confidence & ease.

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
            if self.token_type == "Lien OTP":
                mess = """<#> Dear customer, use the Lien OTP {token} to complete your process of pledging the Mutual Fund holdings.

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
            if self.token_type == "Invoke OTP":
                mess = """<#> Dear customer, Use the Invoke OTP {token} for a hassle-free transaction. Securely sell your Mutual Fund holdings with ease. 

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
            if self.token_type == "Revoke OTP":
                mess = """<#> Dear customer, use OTP {token} to place the revoke request for Mutual Fund holdings. Do not shar OTP for security reasons. Valid for 10 mins

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )

            if self.token_type == "Loan Renewal OTP":
                mess = """<#> Dear customer, Your loan renewal request OTP for Spark Loans is {token}. NEVER share your OTP with anyone. OTP Expires in 10 mins. Thank you!

{otp_hash}
- Spark Loans""".format(
                    token=self.token,
                    otp_hash=las_settings.app_identification_hash_string,
                )
            if mess:
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
                doc=doc,
            )
        elif self.token_type == "Forgot Pin OTP":
            customer = frappe.get_all(
                "Loan Customer", filters={"user": self.entity}, fields=["*"]
            )[0]

            if customer.choice_kyc:
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                full_name = doc.fullname
                if doc.mob_num:
                    mob_num = doc.mob_num
                else:
                    mob_num = doc.ckyc_mob_no
            else:
                doc = frappe.get_doc("User", self.entity).as_dict()
                full_name = doc.full_name
                mob_num = doc.phone

            if doc:
                email_otp = frappe.db.sql(
                    "select message from `tabNotification` where name='Other OTP for Spark Loans';"
                )[0][0]
                email_otp = email_otp.replace("investor_name", full_name)
                email_otp = email_otp.replace(
                    "token_type", self.token_type.replace(" ", "")
                )
                email_otp = email_otp.replace("token", self.token)
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[doc.email],
                    sender=None,
                    subject="OTP for Spark Loans",
                    message=email_otp,
                    queue="short",
                    delayed=False,
                    job_name="Spark OTP on Email",
                )

            msg = """<#> Dear customer, Forgot your PIN? No worries! Use OTP {token} to recover your 4-digit pin.
 
{otp_hash}
- Spark Loans""".format(
                token=self.token,
                otp_hash=las_settings.app_identification_hash_string,
            )
            # lms.send_sms_notification(customer=customer,msg=msg)
            # msg = frappe._(
            #     "Dear Customer, Your {token_type} for Spark Loans is {token}. Do not share your {token_type} with anyone. Your OTP is valid for 10 minutes -Spark Loans"
            # ).format(
            #     token_type=self.token_type.replace(" ", ""),
            #     token=self.token,
            #     # expiry_in_minutes=expiry_in_minutes,
            # )
            if msg:
                # lms.send_sms_notification(customer=customer,msg=msg)
                receiver_list = [str(customer.phone)]
                if mob_num:
                    receiver_list.append(str(mob_num))

                receiver_list = list(set(receiver_list))

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
    arg = {}
    try:

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
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback() + "\n\nArguments:\n" + str(arg),
            title="Send SMS Error",
        )


def send_via_gateway(arg):
    try:
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
    except Exception:
        frappe.log_error()


def get_headers(sms_settings=None):
    if not sms_settings:
        sms_settings = frappe.get_doc("SMS Settings", "SMS Settings")

    headers = {"Accept": "text/plain, text/html, */*"}
    for d in sms_settings.get("parameters"):
        if d.header == 1:
            headers.update({d.parameter: d.value})

    return headers


def send_request(gateway_url, params, headers=None, use_post=False):
    log = {}
    try:
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
        if type(params["sms"]) == bytes:
            params["sms"] = params["sms"].decode("ascii")
        log = {
            "url": gateway_url,
            "params": params,
            "response": response.json(),
        }
        lms.create_log(log, "sms_log")
        # SMS LOG end
        response.raise_for_status()
        return response.status_code
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback() + "\n\nSMS details:\n" + str(log)
            if log
            else params,
            title="Send sms request error",
        )


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
