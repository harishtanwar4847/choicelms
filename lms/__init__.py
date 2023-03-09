# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import base64
import calendar
import datetime
import hashlib
import hmac
import io
import json
import math
import os
import re
import subprocess
from base64 import b64decode, b64encode
from datetime import datetime, timedelta
from distutils.version import LooseVersion
from inspect import currentframe
from itertools import groupby
from random import choice, randint, randrange
from traceback import format_exc

import frappe
import numpy_financial as npf
import pdfkit
import razorpay
import requests
import six
import utils
import xmltodict
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from frappe import _
from frappe.utils import scrub_urls

# from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.utils.csvutils import read_csv_content
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from razorpay.errors import SignatureVerificationError
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from lms.config import lms
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.user_token.user_token import send_sms

from .exceptions import *

# from lms.exceptions.CustomerNotFoundException import CustomerNotFoundException
# from lms.exceptions.InvalidUserTokenException import InvalidUserTokenException
# from lms.exceptions.UserKYCNotFoundException import UserKYCNotFoundException

# from lms.exceptions.UserNotFoundException import UserNotFoundException

__version__ = "5.13.8"

user_token_expiry_map = {
    "OTP": 10,
    # "Email Verification Token": 60,
    "Pledge OTP": 10,
    "Withdraw OTP": 10,
    "Unpledge OTP": 10,
    "Sell Collateral OTP": 10,
    "Forgot Pin OTP": 10,
    "Lien OTP": 10,
    "Invoke OTP": 10,
    "Revoke OTP": 10,
}


def after_install():
    frappe.db.set_value(
        "System Settings", "System Settings", "allow_consecutive_login_attempts", 3
    )

    frappe.db.set_value(
        "Contact Us Settings", None, "forward_to_email", "erp@atritechnocrat.in"
    )


class ValidationError(Exception):
    http_status_code = 422


class ServerError(Exception):
    http_status_code = 500


class FirebaseError(Exception):
    pass


class FirebaseCredentialsFileNotFoundError(FirebaseError):
    pass


class InvalidFirebaseCredentialsError(FirebaseError):
    pass


class FirebaseTokensNotProvidedError(FirebaseError):
    pass


class FirebaseDataNotProvidedError(FirebaseError):
    pass


def validate_http_method(allowed_method_csv):
    if str(frappe.request.method).upper() not in allowed_method_csv.split(","):
        raise ValidationError(_("{} not allowed.").format(frappe.request.method))


def appErrorLog(title, error):
    d = frappe.get_doc(
        {
            "doctype": "App Error Log",
            "title": str("User:") + str(title + " " + "App Error"),
            "error": format_exc(),
        }
    )
    d = d.insert(ignore_permissions=True)
    return d


def generateResponse(is_success=True, status=200, message=None, data={}, error=None):
    response = {}
    if is_success:
        response["status"] = int(status)
        response["message"] = message
        response["data"] = data
    else:
        appErrorLog(frappe.session.user, str(error))
        response["status"] = 500
        response["message"] = message or "Something Went Wrong"
        response["data"] = data
    return response


def send_otp(entity):
    try:
        OTP_CODE = random_token(length=4, is_numeric=True)
        otp_doc = create_user_token(entity=entity, token=OTP_CODE)

        if not otp_doc:
            raise ServerError(
                _("There was some problem while sending OTP. Please try again.")
            )
    except Exception as e:
        generateResponse(is_success=False, error=e)
        raise


def verify_user_token(entity, token, token_type):
    filters = {"entity": entity, "token": token, "token_type": token_type, "used": 0}

    token_name = frappe.db.get_value("User Token", filters, "name")

    if not token_name:
        raise InvalidUserTokenException("Invalid {}".format(token_type))

    return frappe.get_doc("User Token", token_name)


def token_mark_as_used(token):
    if token.used == 0:
        token.used = 1
        token.save(ignore_permissions=True)
        frappe.db.commit()


def check_user_token(entity, token, token_type):
    if token_type == "Firebase Token":
        otp_list = frappe.db.get_all(
            "User Token",
            {"entity": entity, "token_type": token_type, "token": token, "used": 0},
        )
    else:
        otp_list = frappe.db.get_all(
            "User Token",
            {
                "entity": entity,
                "token_type": token_type,
                "token": token,
                "used": 0,
                "expiry": (">", frappe.utils.now_datetime()),
            },
        )

    if len(otp_list) == 0:
        return False, None

    return True, otp_list[0].name


def get_firebase_tokens(entity):
    token_list = frappe.db.get_all(
        "User Token",
        filters={"entity": entity, "token_type": "Firebase Token", "used": 0},
        fields=["token"],
    )

    return [i.token for i in token_list]


def get_user(input, throw=False):
    user_data = frappe.db.sql(
        """select name from `tabUser` where email=%s or phone=%s""",
        (input, input),
        as_dict=1,
    )
    if len(user_data) >= 1:
        return user_data[0].name
    else:
        if throw:
            raise ValidationError(_("Mobile no. does not exist."))
        return False


def __user(input=None):
    # get session user if input is not provided
    if not input:
        input = frappe.session.user
    res = frappe.get_all("User", or_filters={"email": input, "username": input})

    if len((res)) == 0:
        raise UserNotFoundException

    return frappe.get_doc("User", res[0].name)


def generate_user_secret(user_name):
    """
    generate api key and api secret

    :param user: str
    """
    user_details = frappe.get_doc("User", user_name)
    api_secret = frappe.generate_hash(length=15)
    # if api key is not set generate api key
    if not user_details.api_key:
        api_key = frappe.generate_hash(length=15)
        user_details.api_key = api_key
    user_details.api_secret = api_secret
    user_details.save(ignore_permissions=True)
    return api_secret


def generate_user_token(user_name):
    secret_key = generate_user_secret(user_name)
    api_key = frappe.db.get_value("User", user_name, "api_key")

    return "token {}:{}".format(api_key, secret_key)


def create_user(first_name, last_name, mobile, email, tester):
    try:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "username": mobile,
                "phone": mobile,
                "mobile_no": mobile,
                "send_welcome_email": 0,
                "new_password": frappe.mock("password"),
                "roles": [
                    {"doctype": "Has Role", "role": "Loan Customer"},
                    {"doctype": "Has Role", "role": "Spark Tester"},
                ]
                if tester
                else [{"doctype": "Has Role", "role": "Loan Customer"}],
            }
        ).insert(ignore_permissions=True)

        return user
    except Exception as e:
        raise utils.exceptions.APIException(message=str(e))


def create_customer(user):
    try:
        customer = frappe.get_doc(
            {"doctype": "Loan Customer", "user": user.email}
        ).insert(ignore_permissions=True)

        return customer
    except Exception as e:
        raise utils.exceptions.APIException(message=str(e))


def add_user(first_name, last_name, phone, email):
    try:
        user = frappe.get_doc(
            dict(
                doctype="User",
                email=email,
                first_name=first_name,
                last_name=last_name,
                username=str(phone),
                phone=phone,
                mobile_no=phone,
                send_welcome_email=0,
                new_password="{0}-{0}".format(
                    frappe.utils.now_datetime().strftime("%s")
                ),
                roles=[{"doctype": "Has Role", "role": "Loan Customer"}],
            )
        ).insert(ignore_permissions=True)

        customer = frappe.get_doc(
            dict(doctype="Loan Customer", user=user.email)
        ).insert(ignore_permissions=True)

        create_user_token(
            entity=email, token=random_token(), token_type="Email Verification Token"
        )

        return user.name
    except Exception:
        return False


def is_float_num_valid(num, length, precision):
    valid = True

    valid = True if type(num) is float else False

    num_str = str(num)
    if valid:
        valid = True if len(num_str.replace(".", "")) <= length else False

    if valid:
        valid = True if len(num_str.split(".")[1]) <= precision else False

    return valid


def get_cdsl_prf_no():
    return "PF{}".format(frappe.utils.now_datetime().strftime("%s"))


def convert_list_to_tuple_string(list_):
    tuple_string = ""

    for i in list_:
        tuple_string += "'{}',".format(i)

    return "({})".format(tuple_string[:-1])


def get_security_prices(securities=None):
    # sauce: https://stackoverflow.com/a/10030851/9403680
    if securities:
        query = """select security, price, time from `tabSecurity Price` inner join (
			select security as security_, max(time) as latest from `tabSecurity Price` where security in {} group by security_
			) res on time = res.latest and security = res.security_;""".format(
            convert_list_to_tuple_string(securities)
        )
        results = frappe.db.sql(query, as_dict=1)
    else:
        query = """select security, price, time from `tabSecurity Price` inner join (
			select security as security_, max(time) as latest from `tabSecurity Price` group by security_
			) res on time = res.latest and security = res.security_;"""
        results = frappe.db.sql(query, as_dict=1)

    price_map = {}

    for r in results:
        price_map[r.security] = r.price

    return price_map


def get_security_categories(securities, lender, instrument_type="Shares"):
    select = "isin, security_category"
    if instrument_type == "Mutual Fund":
        select += ", scheme_type"
    query = """select {} from `tabAllowed Security`
				where
				lender = '{}' and
                instrument_type = '{}' and
				isin in {}""".format(
        select, lender, instrument_type, convert_list_to_tuple_string(securities)
    )

    results = frappe.db.sql(query, as_dict=1)

    security_map = {}

    for r in results:
        security_map[r.isin] = r.category

    return security_map


def get_allowed_securities(securities, lender, instrument_type="Shares"):

    select = "als.isin, als.security_name, als.eligible_percentage, sc.category_name as security_category, als.lender"
    allowed = ""
    if instrument_type == "Mutual Fund":
        select += ", als.scheme_type, als.amc_code, als.allowed"
        allowed = "and als.allowed = 1"

    if type(lender) == list:
        filter = "in {}".format(convert_list_to_tuple_string(lender))
    else:
        filter = "= '{}'".format(lender)

    query = """select
				{select}
				from `tabAllowed Security` als
                LEFT JOIN `tabSecurity Category` sc
				ON als.security_category = sc.name where
				als.lender {lender} 
                {allowed} and
                als.instrument_type = '{instrument_type}' and
                als.isin in {isin}""".format(
        select=select,
        lender=filter,
        allowed=allowed,
        instrument_type=instrument_type,
        isin=convert_list_to_tuple_string(securities),
    )

    results = frappe.db.sql(query, as_dict=1)

    security_map = {}

    for r in results:
        security_map[r.isin] = r

    return security_map


def chunk_doctype(doctype, limit=50):
    total = frappe.db.count(doctype)
    chunks = range(0, total, limit)

    return {"total": total, "limit": limit, "chunks": chunks}


def __customer(entity=None):
    res = frappe.get_all("Loan Customer", filters={"user": __user(entity).name})
    if len(res) == 0:
        raise CustomerNotFoundException

    return frappe.get_doc("Loan Customer", res[0].name)


def __user_kyc(entity=None, pan_no=None, throw=True):
    filters = {"user": __user(entity).name, "consent_given": 1}
    if pan_no:
        filters["pan_no"] = pan_no
    res = frappe.get_all("User KYC", filters=filters, order_by="creation desc")

    if len(res) == 0:
        if throw:
            raise UserKYCNotFoundException
        return frappe.get_doc({"doctype": "User KYC", "user": filters["user"]})

    return frappe.get_doc("User KYC", res[0].name)


def __banks(user_kyc=None):
    if not user_kyc:
        user_kyc = __user_kyc().name

    res = frappe.get_all(
        "User Bank Account",
        filters={"parent": user_kyc},
        fields=["*"],
        order_by="is_default desc",
    )
    # for i in res:
    #     i.account_number = user_details_hashing(i.account_number)

    for i in res:
        i.account_number = user_details_hashing(i.account_number)
        i.creation = str(i.creation)
        i.modified = str(i.modified)

    return res


def round_down_amount_to_nearest_thousand(amount):
    return float(int(amount / 1000) * 1000)


def get_customer(entity):
    customer_list = frappe.get_all("Loan Customer", filters={"user": get_user(entity)})
    return frappe.get_doc("Loan Customer", customer_list[0].name)


def delete_user(doc, method):
    frappe.db.sql("delete from `tabUser KYC` where user = %s", doc.name)
    frappe.db.sql("delete from `tabLoan Customer` where user = %s", doc.name)
    frappe.db.sql("delete from `tabWorkflow Action` where user = %s", doc.name)
    frappe.db.commit()


def add_firebase_token(firebase_token, app_version_platform, user=None):
    if not user:
        user = frappe.session.user

    old_token_name = frappe.get_all(
        "User Token",
        filters={"entity": user, "token_type": "Firebase Token"},
        order_by="creation desc",
        fields=["*"],
        page_length=1,
    )
    if old_token_name:
        old_token = frappe.get_doc("User Token", old_token_name[0].name)
        token_mark_as_used(old_token)

    get_user_token = frappe.db.get_value(
        "User Token",
        {"token_type": "Firebase Token", "token": firebase_token, "entity": user},
    )
    if get_user_token:
        return

    create_user_token(
        entity=user,
        token=firebase_token,
        token_type="Firebase Token",
        app_version_platform=app_version_platform,
    )


def create_user_token(entity, token, token_type="OTP", app_version_platform=""):
    doc_data = {
        "doctype": "User Token",
        "entity": entity,
        "token": token,
        "token_type": token_type,
    }

    expiry_in_minutes = user_token_expiry_map.get(token_type, None)
    if expiry_in_minutes:
        # expire previous OTPs
        frappe.db.sql(
            """
			update `tabUser Token` set expiry = CURRENT_TIMESTAMP
			where entity = '{entity}' and token_type = '{token_type}' and used = 0 and expiry > CURRENT_TIMESTAMP;
		""".format(
                entity=entity, token_type=token_type
            )
        )
        doc_data["expiry"] = frappe.utils.now_datetime() + timedelta(
            minutes=expiry_in_minutes
        )

    if app_version_platform:
        doc_data["app_version_platform"] = app_version_platform
        doc_data["customer_id"] = frappe.db.get_value(
            "Loan Customer", {"user": entity}, "name"
        )

    user_token = frappe.get_doc(doc_data)
    user_token.save(ignore_permissions=True)

    return user_token


def save_signed_document(file_id, doctype, docname):
    las_settings = frappe.get_single("LAS Settings")
    loan_aggrement_file = las_settings.esign_download_signed_file_url.format(
        file_id=file_id
    )
    file_ = frappe.get_doc(
        {
            "doctype": "File",
            "attached_to_doctype": doctype,
            "attached_to_name": docname,
            "file_url": loan_aggrement_file,
            "file_name": "loan-aggrement.pdf",
        }
    )
    file_.insert(ignore_permissions=True)


def amount_formatter(amount):
    amount = amount or 0
    denominations = {100000: "L", 10000000: "Cr", 1000000000: "Ar", 100000000000: "Kr"}

    amounts = sorted(denominations.keys())
    # amounts.sort()

    if amount < amounts[0]:
        return "{:,.2f}".format(amount)

    formatted_amount = None
    denomination = None
    for i in amounts:
        res = float(amount) / i
        if res >= 1:
            formatted_amount = str(res)
            denomination = i
        else:
            break

    formatted_amount = formatted_amount[: formatted_amount.index(".") + 3]

    return "{} {}".format(formatted_amount, denominations.get(denomination))


def random_token(length=10, is_numeric=False):
    import random
    import string

    if is_numeric:
        sample_str = "".join((random.choice(string.digits) for i in range(length)))
    else:
        letters_count = random.randrange(length)
        digits_count = length - letters_count

        sample_str = "".join(
            (random.choice(string.ascii_letters) for i in range(letters_count))
        )
        sample_str += "".join(
            (random.choice(string.digits) for i in range(digits_count))
        )

    # Convert string to list and shuffle it to mix letters and digits
    sample_list = list(sample_str)
    random.shuffle(sample_list)
    final_string = "".join(sample_list)
    return final_string


def user_dashboard(data=None):
    return {
        "fieldname": "user",
        "transactions": [
            {"items": ["Loan Customer"]},
        ],
    }


def regex_special_characters(search, regex=None):
    if regex:
        regex = regex
    else:
        regex = re.compile("[@_!#$%^&*()<>?/\|}{~:`]")

    if regex.search(search) != None:
        return True
    else:
        return False


def date_str_format(date=None):
    # date formatting in html to pdf
    # 1 => 1st, 11 => 11th, 21 => 21st
    # 2 => 2nd, 12 => 12th, 22 => 22nd
    # 3 => 3rd, 13 => 13th, 23 => 23rd
    # 4 => 4th, 14 => 14th, 24 => 24th

    if 10 <= date % 100 < 20:
        return str(date) + "th"
    else:
        return str(date) + {1: "st", 2: "nd", 3: "rd"}.get(date % 10, "th")


def web_mail(notification_name, name, recepient, subject):
    mail_content = frappe.db.sql(
        "select message from `tabNotification` where name='{}';".format(
            notification_name
        )
    )[0][0]
    mail_content = mail_content.replace(
        "user_name",
        "{}".format(name),
    )
    mail_content = mail_content.replace(
        "logo_file",
        frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
    )
    mail_content = mail_content.replace(
        "fb_icon",
        frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
    )
    mail_content = mail_content.replace(
        "tw_icon",
        frappe.utils.get_url("/assets/lms/mail_images/tw-icon.png"),
    )
    mail_content = mail_content.replace(
        "inst_icon",
        frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
    )
    mail_content = (
        mail_content.replace(
            "lin_icon", frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png")
        ),
    )
    frappe.enqueue(
        method=frappe.sendmail,
        recipients=["{}".format(recepient)],
        sender=None,
        subject="{}".format(subject),
        message=mail_content[0],
    )


def create_log(log, file_name):
    try:
        log_file = frappe.utils.get_files_path("{}.json".format(file_name))
        logs = None
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                logs = f.read()
            f.close()
        logs = json.loads(logs or "[]")
        log["req_time"] = str(frappe.utils.now_datetime())
        logs.append(log)
        with open(log_file, "w") as f:
            f.write(json.dumps(logs))
        f.close()
    except json.decoder.JSONDecodeError:
        log_text_file = (
            log_file.replace(".json", "") + str(frappe.utils.now_datetime()) + ".txt"
        ).replace(" ", "-")
        with open(log_text_file, "w") as txt_f:
            txt_f.write(logs + "\nLast Log \n" + str(log))
        txt_f.close()
        os.remove(log_file)
        frappe.log_error(
            message=frappe.get_traceback()
            + "\n\nFile name -\n{}\n\nLog details -\n{}".format(file_name, str(log)),
            title="Create Log JSONDecodeError",
        )
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback()
            + "\n\nFile name -\n{}\n\nLog details -\n{}".format(file_name, str(log)),
            title="Create Log Error",
        )


def send_spark_push_notification(
    fcm_notification={}, message="", loan="", customer=None
):
    try:
        fcm_payload = {}
        tokens = get_firebase_tokens(customer.user)
        if fcm_notification and tokens:
            if message:
                message = message
            else:
                message = fcm_notification.message

            try:
                random_id = randint(1, 2147483646)
                current_time = frappe.utils.now_datetime()
                notification_name = (str(random_id) + " " + str(current_time)).replace(
                    " ", "-"
                )
                sound = "default"
                priority = "high"

                fcm_payload = {
                    "registration_ids": tokens,
                    "priority": priority,
                }

                notification = {
                    "title": fcm_notification.title,
                    "body": message,
                    "sound": sound,
                }

                data = {
                    "click_action": "FLUTTER_NOTIFICATION_CLICK",
                    "name": notification_name,
                    "notification_id": str(random_id),
                    "screen": fcm_notification.screen_to_open,
                    "loan_no": loan if loan else "",
                    "title": fcm_notification.title,
                    "body": message,
                    "notification_type": fcm_notification.notification_type,
                    "time": current_time.strftime("%d %b at %H:%M %p"),
                }
                android = {"priority": priority, "notification": {"sound": sound}}
                apns = {
                    "payload": {"aps": {"sound": sound, "contentAvailable": True}},
                    "headers": {
                        "apns-push-type": "background",
                        "apns-priority": "5",
                        "apns-topic": "io.flutter.plugins.firebase.messaging",
                    },
                }

                fcm_payload["notification"] = notification
                fcm_payload["data"] = data
                fcm_payload["android"] = android
                fcm_payload["apns"] = apns

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": "key=AAAAennLf7s:APA91bEoQFxqyBP87PXSVS3nXYGhVwh0-5CXQyOzEW8vwKiRqYw-5y2yPXIFWvQ9-Mr0rHeS2NWdq43ogeH76esO3GJyZCEQs2mOgUk6RStxW-hgsioIAJaaiidov8xDg1-yyTn_JCYQ",
                }
                url = "https://fcm.googleapis.com/fcm/send"
                res = requests.post(
                    url=url,
                    data=json.dumps(fcm_payload),
                    headers=headers,
                )
                res_json = json.loads(res.text)
                log = {
                    "url": url,
                    "headers": headers,
                    "request": data,
                    "response": res_json,
                }

                create_log(log, "Send_Spark_Push_Notification_Log")

                # fa.send_android_message(
                #     title=fcm_notification.title,
                #     body=message,
                #     data=data,
                #     tokens=get_firebase_tokens(customer.user),
                #     priority="high",
                # )
                if res.ok and res.status_code == 200:
                    # Save log for Spark Push Notification
                    frappe.get_doc(
                        {
                            "doctype": "Spark Push Notification Log",
                            "name": notification_name,
                            "title": data["title"],
                            "loan_customer": customer.name,
                            "customer_name": customer.full_name,
                            "loan": data["loan_no"],
                            "screen_to_open": data["screen"],
                            "notification_id": data["notification_id"],
                            "notification_type": data["notification_type"],
                            "time": current_time,
                            "click_action": data["click_action"],
                            "message": data["body"],
                            "is_cleared": 0,
                            "is_read": 0,
                        }
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
            except (
                requests.RequestException,
                TypeError,
                KeyError,
                ValueError,
                FirebaseError,
            ):
                # To log fcm notification Exception into Frappe Error Log
                raise Exception
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback()
            + "\nNotification Info:\n"
            + json.dumps(fcm_payload if fcm_payload else customer.name),
            title="Spark Push Notification Error",
        )


def validate_rupees(type_of_fees):
    process_charge = type_of_fees
    process_charge = str(process_charge)
    arr = process_charge.split(".")

    if arr[1] == "0":
        return int(type_of_fees)
    else:
        return "{:.2f}".format(float(type_of_fees))


def validate_percent(type_of_fees):
    process_charge = type_of_fees
    process_charge = str(process_charge)
    arr = process_charge.split(".")

    if arr[1] == "0":
        return int(type_of_fees)
    else:
        return "{:.2f}".format(float(type_of_fees))


def number_to_word(number):
    def get_word(n):
        words = {
            0: "",
            1: "One",
            2: "Two",
            3: "Three",
            4: "Four",
            5: "Five",
            6: "Six",
            7: "Seven",
            8: "Eight",
            9: "Nine",
            10: "Ten",
            11: "Eleven",
            12: "Twelve",
            13: "Thirteen",
            14: "Fourteen",
            15: "Fifteen",
            16: "Sixteen",
            17: "Seventeen",
            18: "Eighteen",
            19: "Nineteen",
            20: "Twenty",
            30: "Thirty",
            40: "Forty",
            50: "Fifty",
            60: "Sixty",
            70: "Seventy",
            80: "Eighty",
            90: "Ninty",
        }
        if n <= 20:
            return words[n]
        else:
            ones = n % 10
            tens = n - ones
            return words[tens] + " " + words[ones]

    def get_all_word(n):
        d = [100, 10, 100, 100]
        v = ["", "Hundred And", "Thousand", "lakh"]
        w = []
        for i, x in zip(d, v):
            t = get_word(n % i)
            if t != "":
                t += " " + x
            w.append(t.rstrip(" "))
            n = n // i
        w.reverse()
        w = " ".join(w).strip()
        if w.endswith("And"):
            w = w[:-3]
        return w

    number1 = float(number)
    arr = str(number).split(".")
    number = int(arr[0])
    crore = number // 10000000
    number = number % 10000000
    word = ""
    if number1 > 1:
        if crore > 0:
            word += get_all_word(crore)
            word += " crore "
        word += "Rupees " + get_all_word(number).strip()
        if len(arr) > 1:
            if len(arr[1]) == 1:
                arr[1] += "0"
            word += " and " + get_all_word(int(arr[1])) + " paise"
    elif number1 == 1:
        if crore > 0:
            word += get_all_word(crore)
            word += " crore "
        word += "Rupee " + get_all_word(number).strip()
        if len(arr) > 1:
            if len(arr[1]) == 1:
                arr[1] += "0"
            word += " and " + get_all_word(int(arr[1])) + " paise"
    elif number == 0:
        if len(arr) > 1:
            if len(arr[1]) == 1:
                arr[1] += "0"
            # word +="Rupees "+ get_all_word(int(arr[1])) + " paise"
            word += get_all_word(int(arr[1])) + " paise"
    return word


@frappe.whitelist(allow_guest=True)
def nsdl_success_callback(**kwargs):
    try:
        log = {
            "request": frappe.local.form_dict,
            "headers": {k: v for k, v in frappe.local.request.headers.items()},
        }
        create_log(log, "nsdl__success_log")
        return log

    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist(allow_guest=True)
def nsdl_failure_callback(**kwargs):
    try:
        log = {
            "request": frappe.local.form_dict,
            "headers": {k: v for k, v in frappe.local.request.headers.items()},
        }
        create_log(log, "nsdl__failure_log")
        return log

    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist(allow_guest=True)
def razorpay_callback(**kwargs):
    try:
        log = {
            "request": frappe.local.form_dict,
            "headers": {k: v for k, v in frappe.local.request.headers.items()},
        }
        create_log(log, "razorpay_callback_log")
        return log

    except utils.exceptions.APIException as e:
        return e.respond()


def rupees_to_words(num):
    under_20 = [
        "Zero",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]
    tens = [
        "Twenty",
        "Thirty",
        "Forty",
        "Fifty",
        "Sixty",
        "Seventy",
        "Eighty",
        "Ninety",
    ]
    above_100 = {
        100: "hundred",
        1000: "thousand",
        100000: "lakh",
        10000000: "crore",
        1000000000: "billion",
    }

    if num < 20:
        return under_20[(int)(num)]

    if num < 100:
        return tens[(int)(num / 10) - 2] + (
            "" if num % 10 == 0 else " " + under_20[(int)(num % 10)]
        )

    # find the appropriate pivot - 'Million' in 3,603,550, or 'Thousand' in 603,550
    pivot = max([key for key in above_100.keys() if key <= num])
    if ((int)(num / pivot)) == 1:
        amt_str = (
            str((int)(num / pivot))
            + " "
            + above_100[pivot]
            + ("" if num % pivot == 0 else " " + rupees_to_words(num % pivot))
        )
    else:
        amt_str = (
            str((int)(num / pivot))
            + " "
            + above_100[pivot]
            + "s"
            + ("" if num % pivot == 0 else " " + rupees_to_words(num % pivot))
        )
    return amt_str


def convert_sec_to_hh_mm_ss(seconds):
    min, sec = divmod(seconds, 60)
    hour, min = divmod(min, 60)
    return "%d:%02d:%02d" % (hour, min, sec)


def holiday_list(is_bank_holiday=0, is_market_holiday=0):
    date_list = []
    filters = {}
    if is_bank_holiday:
        filters["is_bank_holiday"] = 1
    elif is_market_holiday:
        filters["is_market_holiday"] = 1

    holiday_list = frappe.get_all(
        "Spark Holiday", filters=filters, fields="date", order_by="date asc"
    )
    for i, dates in enumerate(d["date"] for d in holiday_list):
        date_list.append(dates)

    return list(set(date_list))


def validate_spark_dummy_account(mobile, email="", check_valid=False):
    if check_valid and email:
        return frappe.db.exists(
            {"doctype": "Spark Dummy Account", "mobile": mobile, "email": email}
        )
    else:
        return frappe.db.exists({"doctype": "Spark Dummy Account", "mobile": mobile})


def validate_spark_dummy_account_token(mobile, token, token_type="OTP"):
    filters = {"mobile": mobile, "otp": token}

    dummy_account_name = frappe.db.get_value("Spark Dummy Account", filters, "name")

    if not dummy_account_name:
        raise InvalidUserTokenException("Invalid {}".format(token_type))

    return frappe.get_doc("Spark Dummy Account", dummy_account_name)


def log_api_error(mess=""):
    try:
        """
        Log API error to Error Log

        This method should be called before API responds the HTTP status code
        """

        # AI ALERT:
        # the title and message may be swapped
        # the better API for this is log_error(title, message), and used in many cases this way
        # this hack tries to be smart about whats a title (single line ;-)) and fixes it
        request_parameters = frappe.local.form_dict
        headers = {k: v for k, v in frappe.local.request.headers.items()}
        customer = frappe.get_all("Loan Customer", filters={"user": __user().name})

        if request_parameters.get("cmd").split(".")[
            -1
        ] == "au_penny_drop" and request_parameters.get("personalized_cheque"):
            personalized_cheque_log(
                request_parameters.get("account_number"),
                request_parameters.get("personalized_cheque"),
                "png",
            )
            request_parameters["personalized_cheque"] = ""
        if len(customer) == 0:
            message = "Request Parameters : {}\n\nHeaders : {}".format(
                str(request_parameters), str(headers)
            )
        else:
            message = (
                "Customer ID : {}\n\nRequest Parameters : {}\n\nHeaders : {}".format(
                    customer[0].name, str(request_parameters), str(headers)
                )
            )

        title = (
            request_parameters.get("cmd").split(".")[-1].replace("_", " ").title()
            + " API Error"
        )

        error = frappe.get_traceback() + "\n\n" + str(mess) + "\n\n" + message
        log = frappe.get_doc(
            dict(doctype="API Error Log", error=frappe.as_unicode(error), method=title)
        ).insert(ignore_permissions=True)
        frappe.db.commit()

        return log

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("API Error Log Error"),
        )


@frappe.whitelist(allow_guest=True)
def rzp_payment_webhook_callback(**kwargs):
    try:
        # fetch RZP user
        rzp_user = frappe.db.sql(
            "select u.name from `tabUser` as u left join `tabHas Role` as r on u.email=r.parent where role='Razorpay User'",
            as_dict=1,
        )
        # Webhook event payload
        data = frappe.local.form_dict

        # Razorpay Signature Verification
        webhook_secret = frappe.get_single("LAS Settings").razorpay_webhook_secret

        headers = {k: v for k, v in frappe.local.request.headers.items()}
        if frappe.utils.get_url() == "https://" + headers.get(
            "Host"
        ) or frappe.utils.get_url() == "https://www." + headers.get("Host"):
            webhook_signature = headers.get("X-Razorpay-Signature")
            log = {"rzp_payment_webhook_response": data}
            create_log(log, "rzp_payment_webhook_log")

            expected_signature = hmac.new(
                digestmod="sha256",
                msg=frappe.local.request.data,
                key=bytes(webhook_secret, "utf-8"),
            )
            generated_signature = expected_signature.hexdigest()
            result = hmac.compare_digest(generated_signature, webhook_signature)
            if not result:
                raise SignatureVerificationError(
                    "Razorpay Signature Verification Failed"
                )

            # Assign RZP user session for updating loan transaction
            if rzp_user and result:
                frappe.session.user = rzp_user[0]["name"]

                if (
                    data
                    and len(data) > 0
                    and data["entity"] == "event"
                    and data["event"] in ["payment.captured", "payment.failed"]
                ):
                    # frappe.enqueue(
                    #     method="lms.update_rzp_payment_transaction",
                    #     data=data,
                    #     job_name="Payment Webhook",
                    # )
                    update_rzp_payment_transaction(data)
                else:
                    create_log({"authorized_log": data}, "rzp_authorized_log")
            if not rzp_user:
                frappe.log_error(
                    message=frappe.get_traceback()
                    + "\nWebhook details:\n"
                    + json.dumps(data),
                    title=_("Payment Webhook RZP User not found Error"),
                )
        else:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nWebhook details:\nThis Webhook is not related to the given host.\n"
                + json.dumps(data),
                title=_("Payment Webhook Host Error"),
            )
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback() + "\nWebhook details:\n" + json.dumps(data),
            title=_("Payment Webhook Error"),
        )


def update_rzp_payment_transaction(data):
    try:
        msg = ""
        webhook_main_object = data["payload"]["payment"]["entity"]
        try:
            loan = frappe.get_doc("Loan", webhook_main_object["notes"]["loan_name"])
            customer = frappe.get_doc("Loan Customer", loan.customer)
            payment_transaction_name = frappe.get_value(
                "Loan Transaction",
                {
                    "transaction_type": "Payment",
                    "order_id": webhook_main_object["order_id"],
                    "amount": float(webhook_main_object["notes"].get("amount")),
                    "status": ["in", ["Pending", "Rejected"]],
                    "loan": webhook_main_object["notes"]["loan_name"],
                },
                "name",
            )
        except frappe.DoesNotExistError:
            frappe.log_error(
                message=frappe.get_traceback() + json.dumps(data),
                title=_("Payment Webhook Error - Loan DoesNotExistError"),
            )
            loan = None

        if payment_transaction_name and loan:
            loan_transaction = frappe.get_doc(
                "Loan Transaction", payment_transaction_name
            )
            older_razorpay_event = loan_transaction.razorpay_event
            # Assign RZP event to loan transaction
            # if data["event"] == "payment.authorized":
            #     razorpay_event = "Authorized"
            if data["event"] == "payment.captured":
                razorpay_event = "Captured"
            if data["event"] == "payment.failed":
                razorpay_event = "Failed"
            loan_transaction.transaction_id = webhook_main_object["id"]
            if loan_transaction.razorpay_event != "Captured":
                loan_transaction.razorpay_event = razorpay_event
            if loan_transaction.razorpay_event == "Captured":
                if older_razorpay_event == "Failed" or (
                    loan_transaction.workflow_state == "Rejected"
                    and loan_transaction.razorpay_event == "Captured"
                ):
                    frappe.db.sql(
                        "update `tabLoan Transaction` set status = 'Pending', workflow_state = 'Pending' where name = '{}'".format(
                            payment_transaction_name
                        )
                    )
                    loan_transaction.db_set("workflow_state", "Approved")
                    loan_transaction.db_set("status", "Approved")
                    # loan_transaction.db_set("docstatus",1)
                else:
                    loan_transaction.workflow_state = "Approved"
                    loan_transaction.status = "Approved"
                    loan_transaction.docstatus = 1
            # If RZP event is failed then update the log
            if loan_transaction.razorpay_event == "Captured":
                if older_razorpay_event == "Failed" or (
                    loan_transaction.workflow_state == "Rejected"
                    and loan_transaction.razorpay_event == "Captured"
                ):
                    frappe.db.sql(
                        "update `tabLoan Transaction` set status = 'Pending', workflow_state = 'Pending' where name = '{}'".format(
                            payment_transaction_name
                        )
                    )
                    loan_transaction.db_set("workflow_state", "Approved")
                    loan_transaction.db_set("status", "Approved")
                    # loan_transaction.db_set("docstatus",1)
                else:
                    loan_transaction.workflow_state = "Approved"
                    loan_transaction.status = "Approved"
                    loan_transaction.docstatus = 1
            # If RZP event is failed then update the log
            if loan_transaction.razorpay_event == "Failed":
                loan_transaction.workflow_state = "Rejected"
                loan_transaction.status = "Rejected"
                loan_transaction.razorpay_payment_log = (
                    "<b>code</b> : "
                    + webhook_main_object.get("error_code")
                    + "\n"
                    + "<b>description</b> : "
                    + webhook_main_object.get("error_description")
                    + "\n"
                    + "<b>source</b> : "
                    + webhook_main_object.get("error_source")
                    + "\n"
                    + "<b>step</b> : "
                    + webhook_main_object.get("error_step")
                    + "\n"
                    + "<b>reason</b> : "
                    + webhook_main_object.get("error_reason")
                )
            else:
                loan_transaction.razorpay_payment_log = ""

            # Check user choosed which method to pay
            if webhook_main_object["method"] == "netbanking":
                loan_transaction.bank_name = webhook_main_object["bank"]
                loan_transaction.bank_transaction_id = webhook_main_object[
                    "acquirer_data"
                ]["bank_transaction_id"]

                loan_transaction.name_on_card = ""
                loan_transaction.last_4_digits = ""
                loan_transaction.card_id = ""
                loan_transaction.network = ""

                loan_transaction.vpa = ""

            elif webhook_main_object["method"] == "card":
                loan_transaction.name_on_card = webhook_main_object["card"]["name"]
                loan_transaction.last_4_digits = webhook_main_object["card"]["last4"]
                loan_transaction.card_id = webhook_main_object["card"]["id"]
                loan_transaction.network = webhook_main_object["card"]["network"]

                loan_transaction.bank_name = ""
                loan_transaction.bank_transaction_id = ""

                loan_transaction.vpa = ""

            elif webhook_main_object["method"] == "upi":
                loan_transaction.vpa = webhook_main_object.get("vpa", None)

                loan_transaction.name_on_card = ""
                loan_transaction.last_4_digits = ""
                loan_transaction.card_id = ""
                loan_transaction.network = ""

                loan_transaction.bank_name = ""
                loan_transaction.bank_transaction_id = ""

            loan_transaction.save(ignore_permissions=True)
            frappe.db.commit()

            if (
                loan_transaction.docstatus == 0
                and loan_transaction.razorpay_event == "Captured"
            ):
                loan_transaction.db_set("docstatus", 1)
                loan_transaction.on_submit()

            # Send notification depended on events
            if data["event"] == "payment.captured":
                # if data["event"] == "payment.authorized" or (loan_transaction.razorpay_event == "Captured" and data["event"] != "payment.authorized"):
                # send notification and change loan margin shortfall status to request pending
                if loan_transaction.loan_margin_shortfall:
                    loan_margin_shortfall = frappe.get_doc(
                        "Loan Margin Shortfall", loan_transaction.loan_margin_shortfall
                    )
                    if loan_margin_shortfall.status == "Pending":
                        loan_margin_shortfall.status = "Request Pending"
                        loan_margin_shortfall.save(ignore_permissions=True)
                        frappe.db.commit()
                    doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                    frappe.enqueue_doc(
                        "Notification",
                        "Margin Shortfall Action Taken",
                        method="send",
                        doc=doc,
                    )
                    msg = "Dear Customer,\nThank you for taking action against the margin shortfall.\nYou can view the 'Action Taken' summary on the dashboard of the app under margin shortfall banner. Spark Loans"
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Margin shortfall – Action taken",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )
                # send notification if not loan margin shortfall
                if not loan_transaction.loan_margin_shortfall:
                    doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                    doc["payment"] = {
                        "amount": loan_transaction.amount,
                        "loan": loan.name,
                        "is_failed": 0,
                    }
                    frappe.enqueue_doc(
                        "Notification", "Payment Request", method="send", doc=doc
                    )
                msg = """Dear Customer,\nCongratulations! You payment of Rs. {}  has been successfully received against loan account  {}. It shall be reflected in your account within  24 hours . Spark Loans""".format(
                    loan_transaction.amount, loan.name
                )
            # send notification if rzp event is failed
            if data["event"] == "payment.failed":
                msg = "Dear Customer,\nSorry! Your payment of Rs. {}  was unsuccessful against loan account  {}. Please check with your bank for details. Spark Loans".format(
                    loan_transaction.amount, loan.name
                )
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                doc["payment"] = {
                    "amount": loan_transaction.amount,
                    "loan": loan.name,
                    "is_failed": 1,
                }
                frappe.enqueue_doc(
                    "Notification", "Payment Request", method="send", doc=doc
                )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", "Payment failed", fields=["*"]
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    message=fcm_notification.message.format(
                        amount=loan_transaction.amount,
                        loan=loan.name,
                    ),
                    loan=loan.name,
                    customer=customer,
                )
            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        if not payment_transaction_name:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nWebhook details:\n"
                + json.dumps(data),
                title=_("Payment Webhook Late Authorization Error"),
            )
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback() + "\nWebhook details:\n" + json.dumps(data),
            title=_("Payment Webhook Enqueue Error"),
        )


def cart_permission_query(user):
    if not user:
        user = frappe.session.user
    # todos that belong to user or assigned by user
    # return "(`tabLender`.name = {lender})".format(lender=frappe.db.escape("Demo"))
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabCart`.lender = {lender} or `tabCart`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def loan_application_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabLoan Application`.lender = {lender} or `tabLoan Application`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def collateral_ledger_permission_query(user):
    if not user:
        user = frappe.session.user
    # todos that belong to user or assigned by user
    # return "(`tabLender`.name = {lender})".format(lender=frappe.db.escape("Demo"))
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabCollateral Ledger`.lender = {lender} or `tabCollateral Ledger`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def loan_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabLoan`.lender = {lender} or `tabLoan`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def loan_transaction_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabLoan Transaction`.lender = {lender} or `tabLoan Transaction`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def unpledge_application_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabUnpledge Application`.lender = {lender} or `tabUnpledge Application`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def sell_collateral_application_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabSell Collateral Application`.lender = {lender} or `tabSell Collateral Application`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def top_up_application_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabTop up Application`.lender = {lender} or `tabTop up Application`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def lender_ledger_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabLender Ledger`.lender = {lender} or `tabLender Ledger`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def allowed_security_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabAllowed Security`.lender = {lender} or `tabAllowed Security`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def security_category_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabSecurity Category`.lender = {lender} or `tabSecurity Category`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def lender_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "(`tabLender`.name = {lender} or `tabLender`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def loan_margin_shortfall_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "((`tabLoan Margin Shortfall`.loan in (select name from `tabLoan` where `tabLoan`.lender = {lender})) or `tabLoan Margin Shortfall`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def virtual_interest_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "((`tabVirtual Interest`.loan in (select name from `tabLoan` where `tabLoan`.lender = {lender})) or `tabVirtual Interest`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def interest_configuration_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "((`tabInterest Configuration`.loan in (select name from `tabLoan` where `tabLoan`.lender = {lender})) or `tabInterest Configuration`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


def loan_payment_log_permission_query(user):
    if not user:
        user = frappe.session.user
    user_doc = frappe.get_doc("User", user).as_dict()
    if "Lender" in [r.role for r in user_doc.roles]:
        if user_doc.get("lender"):
            return "((`tabLoan Payment Log`.loan in (select name from `tabLoan` where `tabLoan`.lender = {lender})) or `tabLoan Payment Log`._assign like '%{user_session}%')".format(
                lender=frappe.db.escape(user_doc.lender), user_session=user
            )


@frappe.whitelist(allow_guest=True)
def decrypt_lien_marking_response():
    try:
        data = frappe.local.form_dict
        las_settings = frappe.get_single("LAS Settings")
        encrypted_response = (
            data.get("lienresponse").replace("-", "+").replace("_", "/")
        )

        decrypted_response = AESCBC(
            las_settings.decryption_key, las_settings.iv
        ).decrypt(encrypted_response)

        data = xmltodict.parse(decrypted_response)
        dict_payload = json.loads(json.dumps(data))
        res = dict_payload.get("response")

        log = {
            "encrypted_response": str(encrypted_response),
            "decrypted_response": res,
        }
        create_log(log, "lien_marking_response")
        if (
            res.get("errorcode") == "S000"
            and res.get("error") == "Lien marked sucessfully"
        ):
            frappe.session.user = frappe.get_doc(
                "Loan Customer", res.get("addinfo2")
            ).user
            cart = frappe.get_doc("Cart", res.get("addinfo1"))
            cart.reload()
            # frappe.db.begin()
            cart.lien_reference_number = res.get("lienrefno")
            cart.items = []
            schemes = res.get("schemedetails").get("scheme")
            if type(schemes) != list:
                schemes = [schemes]

            for i in schemes:
                cart.append(
                    "items",
                    {
                        "isin": i["isinno"],
                        "folio": i["folio"],
                        "scheme_code": i["schemecode"],
                        "security_name": i["schemename"],
                        "amc_code": i["amccode"],
                        "pledged_quantity": truncate_float_to_decimals(
                            float(i["lienapprovedunit"]), 3
                        ),
                        "requested_quantity": truncate_float_to_decimals(
                            float(i["lienunit"]), 3
                        ),
                        "type": res.get("bankschemetype"),
                    },
                )
            cart.save(ignore_permissions=True)
            cart.create_loan_application()
            frappe.db.commit()
            return utils.respondWithSuccess()
        else:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nLien Marking Response Details:\n"
                + json.dumps(data),
                title=_("Lien Marking Response Error"),
            )
            return utils.respondWithFailure()
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback()
            + "\nLien Marking Response Details:\n"
            + json.dumps(data),
            title=_("Lien Marking Response Error"),
        )


def create_signature_mycams():
    try:
        las_settings = frappe.get_single("LAS Settings")
        CLIENT_ID = las_settings.client_id
        SECRET_KEY = las_settings.secret_key
        hmac_key = las_settings.hmac_key
        DATE_TIMESTAMP = frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S")

        SIGNATURE = "{}::{}::{}".format(CLIENT_ID, SECRET_KEY, DATE_TIMESTAMP)

        expected_signature = hmac.new(
            digestmod="sha256",
            msg=bytes(SIGNATURE, "utf-8"),
            key=bytes(hmac_key, "utf-8"),
        )
        return DATE_TIMESTAMP, expected_signature.hexdigest()
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback()
            + "\nSignature Details:\n"
            + frappe.session.user
            + str(DATE_TIMESTAMP),
            title=_("MyCAMS Signature Error"),
        )


class AESCBC:
    def __init__(self, key, iv):
        self.key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if len(self.key) > 32:
            self.key = self.key[:32].encode("utf-8")
        self.iv = bytes(iv, "utf-8")

    def encrypt(self, data):
        self.cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        return (
            b64encode(self.cipher.encrypt(pad(data.encode("utf-8"), AES.block_size)))
            .decode("utf-8")
            .replace("+", "-")
            .replace("/", "_")
        )

    def decrypt(self, data):
        raw = b64decode(data)
        self.cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        return unpad(self.cipher.decrypt(raw), AES.block_size).decode("utf-8")


def user_details_hashing(value):
    if len(value) > 4:
        value = value[:2] + len(value[1:-3]) * "X" + value[-2:]
    elif len(value) <= 4 and len(value) > 2:
        value = value[:2] + len(value[2:]) * "X"
    else:
        value = value[:1] + len(value[1:]) * "X"

    return value


def ckyc_dot_net(
    cust, pan_no, is_for_search=False, is_for_download=False, dob="", ckyc_no=""
):
    try:
        las_settings = frappe.get_single("LAS Settings")
        if type(las_settings.ckyc_request_id) != int:
            las_settings.ckyc_request_id = 0
        las_settings.ckyc_request_id = las_settings.ckyc_request_id + 1
        las_settings.save(ignore_permissions=True)
        frappe.db.commit()
        req_data = {
            "idType": "C",
            "idNumber": pan_no,
            "dateTime": datetime.strftime(
                frappe.utils.now_datetime(), "%d-%m-%Y %H:%M:%S"
            ),
            # "requestId": datetime.strftime(frappe.utils.now_datetime(), "%d%m")
            # + str(abs(randint(0, 9999) - randint(1, 99))),
            "requestId": datetime.strftime(frappe.utils.now_datetime(), "%d%m")
            + str(las_settings.ckyc_request_id)[-4:],
        }

        if is_for_search:
            url = las_settings.ckyc_search_api
            log_name = "CKYC_search_api"
            api_type = "CKYC Search"

        if is_for_download and dob and ckyc_no:
            req_data.update({"dob": dob, "ckycNumber": ckyc_no})
            url = las_settings.ckyc_download_api
            log_name = "CKYC_download_api"
            api_type = "CKYC Download"

        headers = {"Content-Type": "application/json"}

        res = requests.post(url=url, headers=headers, data=json.dumps(req_data))
        res_json = json.loads(res.text)

        log = {"url": url, "headers": headers, "request": req_data}
        frappe.get_doc(
            {
                "doctype": "CKYC API Response",
                "ckyc_api_type": api_type,
                "parameters": str(log),
                "response_status": "Success"
                if res_json.get("status") == 200 and not res_json.get("error")
                else "Failure",
                "error": res_json.get("error"),
                "customer": cust.name,
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
        log["response"] = res_json

        create_log(log, log_name)
        if (
            frappe.utils.get_url() == "https://spark.loans"
            and res_json.get("status") != 200
            and res_json.get("error")
        ):
            email_msg = (
                "{customer} CKYC has failed in {api_type} due to Error: {error}".format(
                    customer=cust.name, api_type=api_type, error=res_json.get("error")
                )
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[
                    "manish.prasad@choiceindia.com",
                    "prakash.aare@choiceindia.com",
                    "harsha.sankla@choiceindia.com",
                ],
                sender=None,
                subject="Spark Loans {} failure response".format(api_type),
                message=email_msg,
            )

        return res_json
    except Exception:
        log_api_error(res.text)
        raise Exception


def upload_image_to_doctype(
    customer, seq_no, image_, img_format, img_folder="CKYC_IMG", compress=0
):
    try:
        extra_char = str(randrange(9999, 9999999999))
        img_dir_path = frappe.utils.get_files_path("{}".format(img_folder))

        if not os.path.exists(img_dir_path):
            os.mkdir(img_dir_path)

        picture_file = "{}/{}-{}-{}.{}".format(
            img_folder, customer.full_name, seq_no, extra_char, img_format
        ).replace(" ", "-")

        image_path = frappe.utils.get_files_path(picture_file)
        if os.path.exists(image_path):
            os.remove(image_path)

        ckyc_image_file_path = frappe.utils.get_files_path(picture_file)
        image_decode = base64.decodestring(bytes(str(image_), encoding="utf8"))
        image_file = open(ckyc_image_file_path, "wb").write(image_decode)
        if compress:
            compress_image(ckyc_image_file_path, customer)

        ckyc_image_file_url = frappe.utils.get_url(
            "files/{}/{}-{}-{}.{}".format(
                img_folder, customer.full_name, seq_no, extra_char, img_format
            ).replace(" ", "-")
        )

        return ckyc_image_file_url
    except Exception:
        log_api_error()


def ifsc_details(ifsc=""):
    filters_arr = {}
    if ifsc:
        search_key = str("%" + ifsc + "%")
        filters_arr = {"ifsc": ["like", search_key], "is_active": True}

    return frappe.get_all("Spark Bank Branch", filters_arr, ["*"])


def client_sanction_details(loan, date):
    try:
        customer = frappe.get_doc("Loan Customer", loan.customer)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        interest_config = frappe.get_value(
            "Interest Configuration",
            {
                "to_amount": [">=", loan.sanctioned_limit],
            },
            order_by="to_amount asc",
        )
        int_config = frappe.get_doc("Interest Configuration", interest_config)
        roi_ = int_config.base_interest * 12
        start_date = frappe.db.sql(
            """select cast(creation as date) from `tabLoan` where name = "{}" """.format(
                loan.name
            )
        )
        client_sanction_details = frappe.get_doc(
            dict(
                doctype="Client Sanction Details",
                client_code=customer.name,
                loan_no=loan.name,
                client_name=loan.customer_name,
                pan_no=user_kyc.pan_no,
                creation_date=frappe.utils.now_datetime().date(),
                start_date=start_date,
                end_date=loan.expiry_date,
                sanctioned_amount=loan.sanctioned_limit,
                roi=roi_,
                sanction_date=date,
            ),
        ).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Client Sanction Details"),
        )


@frappe.whitelist()
def system_report_enqueue():
    # daily
    frappe.enqueue(
        method="lms.lms.doctype.client_summary.client_summary.client_summary",
        queue="long",
    )
    frappe.enqueue(
        method="lms.lms.doctype.security_transaction.security_transaction.security_transaction",
        queue="long",
    )
    frappe.enqueue(
        method="lms.lms.doctype.security_exposure_summary.security_exposure_summary.security_exposure_summary",
        queue="long",
    )
    frappe.enqueue(
        method="lms.lms.doctype.security_details.security_details.security_details",
        queue="long",
    )
    curr_date = frappe.utils.now_datetime().date()
    last_date = (curr_date.replace(day=1) + timedelta(days=32)).replace(
        day=1
    ) - timedelta(days=1)
    if curr_date == last_date:
        frappe.enqueue(
            method="lms.lms.doctype.interest_calculation.interest_calculation.interest_calculation_enqueue",
            queue="long",
        )
    frappe.enqueue(
        method="lms.lms.doctype.loan.loan.available_top_up_update",
        queue="long",
    )


def download_file(dataframe, file_name, file_extention, sheet_name):
    file_name = "{}.{}".format(file_name, file_extention)
    file_path = frappe.utils.get_files_path(file_name)
    if os.path.exists(file_path):
        os.remove(file_path)
    file_path = frappe.utils.get_files_path(file_name)
    dataframe.to_excel(file_path, sheet_name=sheet_name, index=False)
    file_url = frappe.utils.get_url("files/{}".format(file_name))
    return file_url


def user_kyc_hashing(user_kyc):
    user_kyc.pan_no = user_details_hashing(user_kyc.pan_no)
    user_kyc.ckyc_no = user_details_hashing(user_kyc.ckyc_no)
    user_kyc.pan = user_details_hashing(user_kyc.pan)
    for i in user_kyc.bank_account:
        i.account_number = user_details_hashing(i.account_number)
    for i in user_kyc.related_person_details:
        i.pan = user_details_hashing(i.pan)
        i.ckyc_no = user_details_hashing(i.ckyc_no)
    for i in user_kyc.identity_details:
        i.ident_num = user_details_hashing(i.ident_num)

    return user_kyc


# Convert datetime into cron expression
def cron_convertor(dt):
    dt_obj = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
    return f"{dt_obj.minute} {dt_obj.hour} {dt_obj.day} {dt_obj.month} *"


def split_list_into_half(a_list):
    half = len(a_list) // 2
    return a_list[:half], a_list[half:]


def get_linenumber():
    cf = currentframe()
    return "line no" + str(cf.f_back.f_lineno)


def ckyc_commit(res_json, customer, dob):
    pid_data = json.loads(res_json.get("data")).get("PID_DATA")

    personal_details = pid_data.get("PERSONAL_DETAILS")
    identity_details = pid_data.get("IDENTITY_DETAILS")
    related_person_details = pid_data.get("RELATED_PERSON_DETAILS")
    image_details = pid_data.get("IMAGE_DETAILS")

    user_kyc = frappe.get_doc(
        {
            "doctype": "User KYC",
            "owner": customer.user,
            "user": customer.user,
            "kyc_type": "CKYC",
            "pan_no": personal_details.get("PAN"),
            "date_of_birth": datetime.strptime(dob, "%d-%m-%Y"),
            "consti_type": personal_details.get("CONSTI_TYPE"),
            "acc_type": personal_details.get("ACC_TYPE"),
            "ckyc_no": personal_details.get("CKYC_NO"),
            "prefix": personal_details.get("PREFIX"),
            "fname": personal_details.get("FNAME"),
            "mname": personal_details.get("MNAME"),
            "lname": personal_details.get("LNAME"),
            "fullname": personal_details.get("FULLNAME"),
            "maiden_prefix": personal_details.get("MAIDEN_PREFIX"),
            "maiden_fname": personal_details.get("MAIDEN_FNAME"),
            "maiden_mname": personal_details.get("MAIDEN_MNAME"),
            "maiden_lname": personal_details.get("MAIDEN_LNAME"),
            "maiden_fullname": personal_details.get("MAIDEN_FULLNAME"),
            "fatherspouse_flag": personal_details.get("FATHERSPOUSE_FLAG"),
            "father_prefix": personal_details.get("FATHER_PREFIX"),
            "father_fname": personal_details.get("FATHER_FNAME"),
            "father_mname": personal_details.get("FATHER_MNAME"),
            "father_lname": personal_details.get("FATHER_LNAME"),
            "father_fullname": personal_details.get("FATHER_FULLNAME"),
            "mother_prefix": personal_details.get("MOTHER_PREFIX"),
            "mother_fname": personal_details.get("MOTHER_FNAME"),
            "mother_mname": personal_details.get("MOTHER_MNAME"),
            "mother_lname": personal_details.get("MOTHER_LNAME"),
            "mother_fullname": personal_details.get("MOTHER_FULLNAME"),
            "gender": personal_details.get("GENDER"),
            "dob": personal_details.get("DOB"),
            "pan": personal_details.get("PAN"),
            "form_60": personal_details.get("FORM_60"),
            "perm_line1": personal_details.get("PERM_LINE1"),
            "perm_line2": personal_details.get("PERM_LINE2"),
            "perm_line3": personal_details.get("PERM_LINE3"),
            "perm_city": personal_details.get("PERM_CITY"),
            "perm_dist": personal_details.get("PERM_DIST"),
            "perm_state": personal_details.get("PERM_STATE"),
            "perm_country": personal_details.get("PERM_COUNTRY"),
            "perm_state_name": frappe.db.get_value(
                "Pincode Master",
                {"state": personal_details.get("PERM_STATE")},
                "state_name",
            ),
            "perm_country_name": frappe.db.get_value(
                "Country Master",
                {"name": personal_details.get("PERM_COUNTRY")},
                "country",
            ),
            "perm_pin": personal_details.get("PERM_PIN"),
            "perm_poa": personal_details.get("PERM_POA"),
            "perm_corres_sameflag": personal_details.get("PERM_CORRES_SAMEFLAG"),
            "corres_line1": personal_details.get("CORRES_LINE1"),
            "corres_line2": personal_details.get("CORRES_LINE2"),
            "corres_line3": personal_details.get("CORRES_LINE3"),
            "corres_city": personal_details.get("CORRES_CITY"),
            "corres_dist": personal_details.get("CORRES_DIST"),
            "corres_state": personal_details.get("CORRES_STATE"),
            "corres_country": personal_details.get("CORRES_COUNTRY"),
            "corres_state_name": frappe.db.get_value(
                "Pincode Master",
                {"state": personal_details.get("CORRES_STATE")},
                "state_name",
            ),
            "corres_country_name": frappe.db.get_value(
                "Country Master",
                {"name": personal_details.get("CORRES_COUNTRY")},
                "country",
            ),
            "corres_pin": personal_details.get("CORRES_PIN"),
            "corres_poa": personal_details.get("CORRES_POA"),
            "resi_std_code": personal_details.get("RESI_STD_CODE"),
            "resi_tel_num": personal_details.get("RESI_TEL_NUM"),
            "off_std_code": personal_details.get("OFF_STD_CODE"),
            "off_tel_num": personal_details.get("OFF_TEL_NUM"),
            "mob_code": personal_details.get("MOB_CODE"),
            "mob_num": personal_details.get("MOB_NUM"),
            "email": personal_details.get("EMAIL"),
            "email_id": personal_details.get("EMAIL"),
            "remarks": personal_details.get("REMARKS"),
            "dec_date": personal_details.get("DEC_DATE"),
            "dec_place": personal_details.get("DEC_PLACE"),
            "kyc_date": personal_details.get("KYC_DATE"),
            "doc_sub": personal_details.get("DOC_SUB"),
            "kyc_name": personal_details.get("KYC_NAME"),
            "kyc_designation": personal_details.get("KYC_DESIGNATION"),
            "kyc_branch": personal_details.get("KYC_BRANCH"),
            "kyc_empcode": personal_details.get("KYC_EMPCODE"),
            "org_name": personal_details.get("ORG_NAME"),
            "org_code": personal_details.get("ORG_CODE"),
            "num_identity": personal_details.get("NUM_IDENTITY"),
            "num_related": personal_details.get("NUM_RELATED"),
            "num_images": personal_details.get("NUM_IMAGES"),
        }
    )

    if user_kyc.gender == "M":
        gender_full = "Male"
    elif user_kyc.gender == "F":
        gender_full = "Female"
    else:
        gender_full = "Transgender"

    user_kyc.gender_full = gender_full

    if identity_details:
        identity = identity_details.get("IDENTITY")
        if identity:
            if type(identity) != list:
                identity = [identity]

            for i in identity:
                user_kyc.append(
                    "identity_details",
                    {
                        "sequence_no": i.get("SEQUENCE_NO"),
                        "ident_type": i.get("IDENT_TYPE"),
                        "ident_num": i.get("IDENT_NUM"),
                        "idver_status": i.get("IDVER_STATUS"),
                        "ident_category": frappe.db.get_value(
                            "Identity Code",
                            {"name": i.get("IDENT_TYPE")},
                            "category",
                        ),
                    },
                )

    if related_person_details:
        related_person = related_person_details.get("RELATED_PERSON")
        if related_person:
            if type(related_person) != list:
                related_person = [related_person]

            for r in related_person:
                photos_ = upload_image_to_doctype(
                    customer=customer,
                    seq_no=r.get("REL_TYPE"),
                    image_=r.get("PHOTO_DATA"),
                    img_format=r.get("PHOTO_TYPE"),
                )
                perm_poi_photos_ = upload_image_to_doctype(
                    customer=customer,
                    seq_no=r.get("REL_TYPE"),
                    image_=r.get("PERM_POI_DATA"),
                    img_format=r.get("PERM_POI_IMAGE_TYPE"),
                )
                corres_poi_photos_ = upload_image_to_doctype(
                    customer=customer,
                    seq_no=r.get("REL_TYPE"),
                    image_=r.get("CORRES_POI_DATA"),
                    img_format=r.get("CORRES_POI_IMAGE_TYPE"),
                )
                user_kyc.append(
                    "related_person_details",
                    {
                        "sequence_no": r.get("SEQUENCE_NO"),
                        "rel_type": r.get("REL_TYPE"),
                        "add_del_flag": r.get("ADD_DEL_FLAG"),
                        "ckyc_no": r.get("CKYC_NO"),
                        "prefix": r.get("PREFIX"),
                        "fname": r.get("FNAME"),
                        "mname": r.get("MNAME"),
                        "lname": r.get("LNAME"),
                        "maiden_prefix": r.get("MAIDEN_PREFIX"),
                        "maiden_fname": r.get("MAIDEN_FNAME"),
                        "maiden_mname": r.get("MAIDEN_MNAME"),
                        "maiden_lname": r.get("MAIDEN_LNAME"),
                        "fatherspouse_flag": r.get("FATHERSPOUSE_FLAG"),
                        "father_prefix": r.get("FATHER_PREFIX"),
                        "father_fname": r.get("FATHER_FNAME"),
                        "father_mname": r.get("FATHER_MNAME"),
                        "father_lname": r.get("FATHER_LNAME"),
                        "mother_prefix": r.get("MOTHER_PREFIX"),
                        "mother_fname": r.get("MOTHER_FNAME"),
                        "mother_mname": r.get("MOTHER_MNAME"),
                        "mother_lname": r.get("MOTHER_LNAME"),
                        "gender": r.get("GENDER"),
                        "dob": r.get("DOB"),
                        "nationality": r.get("NATIONALITY"),
                        "pan": r.get("PAN"),
                        "form_60": r.get("FORM_60"),
                        "add_line1": r.get("Add_LINE1"),
                        "add_line2": r.get("Add_LINE2"),
                        "add_line3": r.get("Add_LINE3"),
                        "add_city": r.get("Add_CITY"),
                        "add_dist": r.get("Add_DIST"),
                        "add_state": r.get("Add_STATE"),
                        "add_country": r.get("Add_COUNTRY"),
                        "add_pin": r.get("Add_PIN"),
                        "perm_poi_type": r.get("PERM_POI_TYPE"),
                        "same_as_perm_flag": r.get("SAME_AS_PERM_FLAG"),
                        "corres_add_line1": r.get("CORRES_ADD_LINE1"),
                        "corres_add_line2": r.get("CORRES_ADD_LINE2"),
                        "corres_add_line3": r.get("CORRES_ADD_LINE3"),
                        "corres_add_city": r.get("CORRES_ADD_CITY"),
                        "corres_add_dist": r.get("CORRES_ADD_DIST"),
                        "corres_add_state": r.get("CORRES_ADD_STATE"),
                        "corres_add_country": r.get("CORRES_ADD_COUNTRY"),
                        "corres_add_pin": r.get("CORRES_ADD_PIN"),
                        "corres_poi_type": r.get("CORRES_POI_TYPE"),
                        "resi_std_code": r.get("RESI_STD_CODE"),
                        "resi_tel_num": r.get("RESI_TEL_NUM"),
                        "off_std_code": r.get("OFF_STD_CODE"),
                        "off_tel_num": r.get("OFF_TEL_NUM"),
                        "mob_code": r.get("MOB_CODE"),
                        "mob_num": r.get("MOB_NUM"),
                        "email": r.get("EMAIL"),
                        "remarks": r.get("REMARKS"),
                        "dec_date": r.get("DEC_DATE"),
                        "dec_place": r.get("DEC_PLACE"),
                        "kyc_date": r.get("KYC_DATE"),
                        "doc_sub": r.get("DOC_SUB"),
                        "kyc_name": r.get("KYC_NAME"),
                        "kyc_designation": r.get("KYC_DESIGNATION"),
                        "kyc_branch": r.get("KYC_BRANCH"),
                        "kyc_empcode": r.get("KYC_EMPCODE"),
                        "org_name": r.get("ORG_NAME"),
                        "org_code": r.get("ORG_CODE"),
                        "photo_type": r.get("PHOTO_TYPE"),
                        "photo": photos_,
                        "perm_poi_image_type": r.get("PERM_POI_IMAGE_TYPE"),
                        "perm_poi": perm_poi_photos_,
                        "corres_poi_image_type": r.get("CORRES_POI_IMAGE_TYPE"),
                        "corres_poi": corres_poi_photos_,
                        "proof_of_possession_of_aadhaar": r.get(
                            "PROOF_OF_POSSESSION_OF_AADHAAR"
                        ),
                        "voter_id": r.get("VOTER_ID"),
                        "nrega": r.get("NREGA"),
                        "passport": r.get("PASSPORT"),
                        "driving_licence": r.get("DRIVING_LICENCE"),
                        "national_poplation_reg_letter": r.get(
                            "NATIONAL_POPLATION_REG_LETTER"
                        ),
                        "offline_verification_aadhaar": r.get(
                            "OFFLINE_VERIFICATION_AADHAAR"
                        ),
                        "e_kyc_authentication": r.get("E_KYC_AUTHENTICATION"),
                    },
                )

    if image_details:
        image_ = image_details.get("IMAGE")
        if image_:
            if type(image_) != list:
                image_ = [image_]

            for im in image_:
                image_data = upload_image_to_doctype(
                    customer=customer,
                    seq_no=im.get("SEQUENCE_NO"),
                    image_=im.get("IMAGE_DATA"),
                    img_format=im.get("IMAGE_TYPE"),
                )
                user_kyc.append(
                    "image_details",
                    {
                        "sequence_no": im.get("SEQUENCE_NO"),
                        "image_type": im.get("IMAGE_TYPE"),
                        "image_code": im.get("IMAGE_CODE"),
                        "global_flag": im.get("GLOBAL_FLAG"),
                        "branch_code": im.get("BRANCH_CODE"),
                        "image_name": frappe.db.get_value(
                            "Document Master",
                            {"name": im.get("IMAGE_CODE")},
                            "document_name",
                        ),
                        "image": image_data,
                    },
                )

    user_kyc.insert(ignore_permissions=True)
    frappe.db.commit()
    return user_kyc


def ckyc_offline(customer, offline_customer):
    res_json = ckyc_dot_net(
        cust=customer,
        pan_no=offline_customer.pan_no,
        is_for_download=True,
        dob=offline_customer.dob,
        ckyc_no=offline_customer.ckyc_no,
    )

    if res_json.get("status") == 200 and not res_json.get("error"):
        try:
            user_kyc = ckyc_commit(
                res_json=res_json, customer=customer, dob=offline_customer.dob
            )

            user_kyc_doc = frappe.get_doc("User KYC", user_kyc.name)

            perm_poa = frappe.db.get_value(
                "Proof of Address Master",
                {"name": user_kyc.perm_poa},
                "poa_name",
            )
            corres_poa = frappe.db.get_value(
                "Proof of Address Master",
                {"name": user_kyc.corres_poa},
                "poa_name",
            )

            ckyc_address_doc = frappe.get_doc(
                {
                    "doctype": "Customer Address Details",
                    "perm_line1": user_kyc.perm_line1,
                    "perm_line2": user_kyc.perm_line2,
                    "perm_line3": user_kyc.perm_line3,
                    "perm_city": user_kyc.perm_city,
                    "perm_dist": user_kyc.perm_dist,
                    "perm_state": user_kyc.perm_state_name,
                    "perm_country": user_kyc.perm_country_name,
                    "perm_pin": user_kyc.perm_pin,
                    "perm_poa": perm_poa,
                    "perm_image": frappe.db.get_value(
                        "CKYC Image Details",
                        {"parent": user_kyc.name, "image_name": perm_poa},
                        "image",
                    ),
                    "corres_poa_image": frappe.db.get_value(
                        "CKYC Image Details",
                        {"parent": user_kyc.name, "image_name": corres_poa},
                        "image",
                    ),
                    "perm_corres_flag": user_kyc.perm_corres_sameflag,
                    "corres_line1": user_kyc.corres_line1,
                    "corres_line2": user_kyc.corres_line2,
                    "corres_line3": user_kyc.corres_line3,
                    "corres_city": user_kyc.corres_city,
                    "corres_dist": user_kyc.corres_dist,
                    "corres_state": user_kyc.corres_state_name,
                    "corres_country": user_kyc.corres_country_name,
                    "corres_pin": user_kyc.corres_pin,
                    "corres_poa": corres_poa,
                }
            ).insert(ignore_permissions=True)
            user_kyc_doc.address_details = ckyc_address_doc.name
            user_kyc_doc.consent_given = 1
            user_kyc_doc.save(ignore_permissions=True)
            kyc_consent_doc = frappe.get_doc(
                {
                    "doctype": "User Consent",
                    "mobile": customer.phone,
                    "consent": "Ckyc",
                }
            )
            kyc_consent_doc.insert(ignore_permissions=True)

            # bank details
            user_kyc_doc.append(
                "bank_account",
                {
                    "bank": offline_customer.bank,
                    "branch": offline_customer.branch,
                    "account_number": offline_customer.account_no,
                    "ifsc": offline_customer.ifsc,
                    "city": offline_customer.city,
                    "account_holder_name": offline_customer.account_holder_name,
                    "bank_address": offline_customer.bank_address,
                    "account_type": offline_customer.account_type,
                },
            ).insert(ignore_permissions=True)
            customer.kyc_update = 1
            customer.choice_kyc = user_kyc.name
            customer.offline_customer = 1
            customer.save(ignore_permissions=True)
            offline_customer.ckyc_status = "Success"
            offline_customer.user_kyc_name = user_kyc.name
            offline_customer.kyc_name = user_kyc.name
            offline_customer.save(ignore_permissions=True)
            frappe.db.commit()

            return offline_customer.ckyc_status

        except Exception as e:
            offline_customer.ckyc_status = "Failure"
            offline_customer.ckyc_remarks = res_json.get("error")
            offline_customer.save(ignore_permissions=True)
            frappe.db.commit()
            log_api_error(mess=str(res_json))
            return utils.respondWithFailure(
                status=res_json.get("status"),
                message="Something went wrong",
                data=str(e),
            )
    else:
        offline_customer.ckyc_status = "Failure"
        offline_customer.ckyc_remarks = res_json.get("error")
        offline_customer.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.db.rollback
        log_api_error(mess=str(res_json))


@frappe.whitelist()
def customer_file_upload(upload_file):
    try:
        files = frappe.get_all("File", filters={"file_url": upload_file}, page_length=1)
        file = frappe.get_doc("File", files[0].name)
        file_path = file.get_full_path()
        with open(file_path, "r") as upfile:
            fcontent = upfile.read()

        csv_data = read_csv_content(fcontent)

        for i in csv_data[1:]:
            message = ""
            # validation for name
            first_name = False
            last_name = False
            if " " in i[0]:
                first_name = True
                message += "Space not allowed in First Name.\n"
            if " " in i[1]:
                last_name = True
                message += "Space not allowed in Last Name.\n"
            reg = regex_special_characters(search=i[0] + i[1])
            if reg:
                message += (
                    "Special Characters not allowed in First Name and Last Name.\n"
                )

            # Validation for Email
            email_regex = (
                r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
            )
            if re.search(email_regex, i[3]) is None or (len(i[3].split("@")) > 2):
                message += "Please enter valid email ID.\n"

            # Validation for Alphanumeric
            alphanum_regex = "^(?=.*[a-zA-Z])(?=.*[0-9])[A-Za-z0-9]+$"
            pan_regex = "[A-Za-z]{5}[0-9]{4}[A-Za-z]{1}"
            if (re.search(pan_regex, i[4]) is None) or (
                re.search(alphanum_regex, i[10]) is None
            ):
                message += "Please enter valid Pan No or IFSC code.\n"

            # validation for mobile number
            if (len(i[2]) > 10) or (i[2].isnumeric == False):
                message += "Please enter valid Mobile Number.\n"

            if (i[6].isnumeric() == False) or (i[9].isnumeric() == False):
                message += "Please enter valid CKYC Number or Account Number.\n"

            # if i[11].isalpha() == False:
            #     message += "Please enter valid city name.\n"

            # entry in Spark offline customer log doctype
            offline_customer = frappe.get_doc(
                dict(
                    doctype="Spark Offline Customer Log",
                    first_name=i[0],
                    last_name=i[1],
                    mobile_no=i[2],
                    email_id=i[3],
                    customer_first_name=i[0],
                    customer_last_name=i[1],
                    customer_mobile=i[2],
                    customer_email=i[3],
                    pan_no=i[4],
                    ckyc_no=i[6],
                    dob=i[5],
                    bank=i[7],
                    # branch=i[8],
                    account_no=i[8],
                    ifsc=i[9],
                    # city=i[11],
                    account_holder_name=i[10],
                    # bank_address=i[13],
                    # account_type=i[11],
                    mycams_email_id=i[11],
                )
            ).insert(ignore_permissions=True)
            frappe.db.commit()

            if (
                (reg)
                or (
                    re.search(email_regex, offline_customer.customer_email) is None
                    or (len(offline_customer.customer_email.split("@")) > 2)
                )
                or (
                    (len(offline_customer.mobile_no) > 10)
                    or offline_customer.mobile_no.isnumeric == False
                )
                or (offline_customer.ckyc_no.isnumeric() == False)
                or (
                    (offline_customer.account_no.isnumeric() == False)
                    or (re.search(alphanum_regex, offline_customer.ifsc) is None)
                )
                or (re.search(pan_regex, offline_customer.pan_no) is None)
                or (first_name)
                or (last_name)
            ):
                offline_customer.user_status = "Failure"
                offline_customer.user_remarks = message
                offline_customer.customer_status = "Failure"
                offline_customer.ckyc_status = "Failure"
                offline_customer.bank_status = "Failure"
                offline_customer.save(ignore_permissions=True)
                frappe.db.commit()
                # frappe.throw(_("Please Enter valid data"))

            else:
                # user creation
                res = frappe.get_all(
                    "User",
                    filters={
                        "phone": offline_customer.mobile_no,
                        "mobile_no": offline_customer.mobile_no,
                    },
                )
                cust = frappe.get_all(
                    "Loan Customer", filters={"phone": offline_customer.mobile_no}
                )
                if res and cust:
                    offline_customer.user_status = "Failure"
                    offline_customer.user_remarks = "Duplicate Value"
                    offline_customer.customer_status = "Failure"
                    offline_customer.customer_remarks = "Duplicate Values"
                    offline_customer.user_name == res[0].name
                    offline_customer.save(ignore_permissions=True)
                    frappe.db.commit()
                else:
                    res_email = frappe.get_all(
                        "User", filters={"email": offline_customer.customer_email}
                    )
                    res_mobile = frappe.get_all(
                        "User",
                        filters={
                            "phone": offline_customer.mobile_no,
                            "mobile_no": offline_customer.mobile_no,
                        },
                    )
                    if res_email or res_mobile:
                        offline_customer.user_status = "Failure"
                        offline_customer.user_remarks = "Duplicate Value"
                        offline_customer.customer_status = "Failure"
                        offline_customer.customer_remarks = "Duplicate Values"
                        offline_customer.user_name == user.name
                        offline_customer.save(ignore_permissions=True)
                        frappe.db.commit()
                    else:
                        user = create_user(
                            offline_customer.first_name,
                            offline_customer.last_name,
                            offline_customer.mobile_no,
                            offline_customer.customer_email,
                            tester=0,
                        )
                        offline_customer.user_status = "Success"
                        offline_customer.user_name == user.name
                        offline_customer.save(ignore_permissions=True)
                        frappe.db.commit()

                    # loan customer creation
                    res = frappe.get_all(
                        "Loan Customer", filters={"phone": offline_customer.mobile_no}
                    )
                    res_user = frappe.get_all(
                        "Loan Customer", filters={"user": user.name}
                    )
                    cust_status = ""
                    if res or res_user:
                        doc_name = res[0].name if res else res_user[0].name
                        frappe.throw(
                            _(
                                "Loan Customer already exists".format(
                                    offline_customer.mobile_no
                                )
                            )
                        )
                        offline_customer.customer_status = "Failure"
                        offline_customer.customer_remarks = "Duplicate Values"
                        offline_customer.user_name == doc_name
                        offline_customer.save(ignore_permissions=True)
                        frappe.db.commit()
                    else:
                        customer = create_customer(user)
                        customer.offline_customer = 1
                        customer.is_email_verified = 1
                        customer.save(ignore_permissions=True)
                        offline_customer.customer_status = "Success"
                        cust_status = "Success"
                        offline_customer.customer_name = customer.name
                        offline_customer.save(ignore_permissions=True)
                        frappe.db.commit()

                    # User Kyc creation
                    res_kyc = frappe.get_all("User KYC", filters={"user": user.name})
                    if res_kyc:
                        frappe.throw(_("User KYC already exists"))
                        offline_customer.ckyc_status = "Failure"
                        offline_customer.ckyc_remarks = "Duplicate Values"
                        offline_customer.user_kyc_name = res_kyc[0].name
                        offline_customer.save(ignore_permissions=True)
                        frappe.db.commit()

                    else:
                        if cust_status == "Success":
                            ckyc_offline(
                                customer=customer, offline_customer=offline_customer
                            )
    except Exception:
        frappe.log_error(
            title="Create User Customer Cron Error",
            message=frappe.get_traceback()
            + "\n\n{}".format(str(i) if i else str(upload_file)),
        )


@frappe.whitelist()
def create_user_customer(upload_file):
    try:
        frappe.enqueue(
            method=customer_file_upload(upload_file=upload_file),
            queue="long",
            job_name="Offline Customer File Processing",
        )
    except Exception:
        frappe.log_error(title="Create User Customer Main Function Error")


def penny_call_create_contact(user=None, customer=None, user_kyc=None):
    try:
        try:
            user_name = user
            if not user:
                user = __user()
                user_name = user.name
        except UserNotFoundException:
            # return utils.respondNotFound(message=frappe._("User not found."))
            # raise exceptions.NotFoundException(_("User not found"))
            data = {"message": "User not found"}
            return data

        # check Loan Customer
        # if not customer:
        customer = __customer(user_name)
        if not customer:
            # return utils.respondNotFound(message=frappe._("Customer not found."))
            # raise exceptions.NotFoundException(_("Customer not found"))
            data = {"message": "Customer not found"}
            return data

        # fetch rzp key secret from las settings and use Basic auth
        las_settings = frappe.get_single("LAS Settings")
        if not las_settings.razorpay_key_secret:
            frappe.log_error(
                title="Penny Drop Create contact Error",
                message="Penny Drop Create contact Error - Razorpay Key Secret Missing",
            )
            # return utils.respondWithFailure()
            data = {
                "message": "Penny Drop Create contact Error - Razorpay Key Secret Missing"
            }
            return data

        razorpay_key_secret_auth = "Basic " + base64.b64encode(
            bytes(las_settings.razorpay_key_secret, "utf-8")
        ).decode("ascii")

        try:
            data_rzp = {
                "name": customer.full_name,
                "email": customer.user,
                "contact": customer.phone,
                "type": "customer",
                "reference_id": customer.name,
                "notes": {},
            }
            raw_res = requests.post(
                las_settings.pennydrop_create_contact,
                headers={
                    "Authorization": razorpay_key_secret_auth,
                    "content-type": "application/json",
                },
                data=json.dumps(data_rzp),
            )
            data_res = raw_res.json()

            if data_res.get("error"):
                log = {
                    "request": data_rzp,
                    "response": data_res.get("error"),
                }
                create_log(log, "rzp_penny_contact_error_log")
                # return utils.respondWithFailure(message=frappe._("failed"))
                data = {"message": "failed"}
                return data

            # User KYC save
            """since CKYC development not done yet, using existing user kyc to update contact ID"""

            # if not user_kyc:
            try:
                user_kyc = __user_kyc(user_name)
            except UserKYCNotFoundException:
                # return utils.respondWithFailure(message=frappe._("User KYC not found"))
                data = {"message": "User KYC not found"}
                return data

            # update contact ID
            contact_id = data_res.get("id")
            create_log(data_res, "rzp_penny_contact_success_log")
            data = {"message": contact_id}
            return data
            # user_kyc.save(ignore_permissions=True)
            # frappe.db.commit()

            # return utils.respondWithSuccess(message=frappe._("success"),data = contact_id)

        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))

    except utils.exceptions.APIException as e:
        log_api_error()
        frappe.log_error(
            title="Penny Drop Create contact Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create contact Error: "
            + str(e.args),
        )
        return e.respond()


def call_penny_create_fund_account(
    user, ifsc=None, account_number=None, account_holder_name=None
):
    try:
        utils.validator.validate_http_method("POST")
        # data = utils.validator.validate(
        #     kwargs,
        #     {
        #         "ifsc": "required",
        #         "account_holder_name": "required",
        #         "account_number": ["required", "decimal"],
        #     },
        # )

        # ifsc and account holder name validation
        reg = regex_special_characters(search=account_holder_name + ifsc)
        if reg:
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            data = {"message": "Special Characters not allowed"}
            return data

        # check user
        try:
            user_name = user
            if not user:
                user = __user()
                user_name = user.name

        except UserNotFoundException:
            # return utils.respondNotFound(message=frappe._("User not found."))
            data = {"message": "User not found"}
            return data

        # fetch rzp key secret from las settings and use Basic auth
        las_settings = frappe.get_single("LAS Settings")
        if not las_settings.razorpay_key_secret:
            frappe.log_error(
                title="Penny Drop Fund Account Error",
                message="Penny Drop Fund Account Error - Razorpay Key Secret Missing",
            )
            # return utils.respondWithFailure()
            data = {
                "message": "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
            }
            return data

        razorpay_key_secret_auth = "Basic " + base64.b64encode(
            bytes(las_settings.razorpay_key_secret, "utf-8")
        ).decode("ascii")

        try:
            user_kyc = __user_kyc(user_name)
        except UserKYCNotFoundException:
            # return utils.respondWithFailure(message=frappe._("User KYC not found"))
            data = {"message": "User KYC not found"}
            return data

        try:
            data_rzp = {
                "contact_id": user_kyc.razorpay_contact_id,
                "account_type": "bank_account",
                "bank_account": {
                    "name": account_holder_name,
                    "ifsc": ifsc,
                    "account_number": account_number,
                },
            }
            raw_res = requests.post(
                las_settings.pennydrop_create_fund_account,
                headers={
                    "Authorization": razorpay_key_secret_auth,
                    "content-type": "application/json",
                },
                data=json.dumps(data_rzp),
            )
            data_res = raw_res.json()
            data = json.dumps(data_rzp)
            if data_res.get("error"):
                log = {
                    "request": data,
                    "response": data_res.get("error"),
                }
                create_log(log, "rzp_penny_fund_account_error_log")
                # return utils.respondWithFailure(message=frappe._("failed"))
                data = {"message": "failed"}
                return data
            # if not get error
            data_resp = {"fa_id": data_res.get("id")}
            create_log(data_res, "rzp_penny_fund_account_success_log")
            return data_resp

        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))

    except utils.exceptions.APIException as e:
        log_api_error()
        frappe.log_error(
            title="Penny Drop Create fund account Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create fund account Error: "
            + str(e.args),
        )
        return e.respond()


def call_penny_create_fund_account_validation(
    user=None,
    create_fund_acc=None,
    account_type=None,
    branch=None,
    city=None,
    personalized_cheque=None,
):
    try:
        # utils.validator.validate_http_method("POST")
        # data = utils.validator.validate(
        #     kwargs,
        #     {
        #         "fa_id": "required",
        #         "bank_account_type": "",
        #         "branch": "required",
        #         "city": "required",
        #         "personalized_cheque": "required",
        #     },
        # )

        # check user
        try:
            user_name = user
            if not user:
                user = __user()
                user_name = user.name
        except UserNotFoundException:
            # return utils.respondNotFound(message=frappe._("User not found."))
            data = {"message": "User not found"}
            return data

        # check Loan Customer
        customer = __customer(user_name)
        if not customer:
            # return utils.respondNotFound(message=frappe._("Customer not found."))
            data = {"message": "Customer not found"}
            return data

        # user KYC
        try:
            user_kyc = __user_kyc(user_name)
        except UserKYCNotFoundException:
            # return utils.respondWithFailure(message=frappe._("User KYC not found"))
            # raise exceptions.RespondWithFailureException(_("User KYC not found"))
            data = {"message": "User KYC not found"}
            return data

        # fetch rzp key secret from las settings and use Basic auth
        las_settings = frappe.get_single("LAS Settings")
        if not las_settings.razorpay_key_secret:
            frappe.log_error(
                title="Penny Drop Fund Account Validation Error",
                message="Penny Drop Fund Account Validation Error - Razorpay Key Secret Missing",
            )
            # return utils.respondWithFailure()
            # raise exceptions.RespondWithFailureException()
            data = {
                "message": "Penny Drop Fund Account Validation Error - Razorpay Key Secret Missing"
            }
            return data

        if not las_settings.razorpay_bank_account:
            frappe.log_error(
                title="Penny Drop Fund Account Validation Error",
                message="Penny Drop Fund Account Validation Error - Razorpay Bank Account Missing",
            )
            # return utils.respondWithFailure()
            raise lms.exceptions.RespondWithFailureException()

        razorpay_key_secret_auth = "Basic " + base64.b64encode(
            bytes(las_settings.razorpay_key_secret, "utf-8")
        ).decode("ascii")

        data = {
            "fa_id": create_fund_acc,
            "bank_account_type": account_type,
            "branch": branch,
            "city": city,
            "personalized_cheque": personalized_cheque,
        }
        try:
            if "rzp_test_" in las_settings.razorpay_key_secret:
                data_res = {
                    "id": "fav_JpHg4DC2VJ80Zw",
                    "entity": "fund_account.validation",
                    "fund_account": {
                        "id": data.get("fa_id"),
                        "entity": "fund_account",
                        "contact_id": "cont_JpHHIYu00BTzNL",
                        "account_type": "bank_account",
                        "bank_account": {
                            "ifsc": "ICIC0000004",
                            "bank_name": "ICICI Bank",
                            "name": "Choice Finserv private limited",
                            "notes": [],
                            "account_number": "000405112507",
                        },
                        "batch_id": None,
                        "active": True,
                        "created_at": 1656935250,
                        "details": {
                            "ifsc": "ICIC0000004",
                            "bank_name": "ICICI Bank",
                            "name": "Choice Finserv private limited",
                            "notes": [],
                            "account_number": "000405112507",
                        },
                    },
                    "status": "completed",
                    "amount": 100,
                    "currency": "INR",
                    "notes": {
                        "branch": data.get("branch"),
                        "city": data.get("city"),
                        "bank_account_type": data.get("bank_account_type"),
                    },
                    "results": {
                        "account_status": "active",
                        "registered_name": user_kyc.fname,
                    },
                    "created_at": 1656936646,
                    "utr": None,
                }

            else:
                data_rzp = {
                    "account_number": las_settings.razorpay_bank_account,
                    "fund_account": {"id": create_fund_acc},
                    "amount": 100,
                    "currency": "INR",
                    "notes": {
                        "branch": branch,
                        "city": city,
                        "bank_account_type": account_type,
                    },
                }
                url = las_settings.pennydrop_create_fund_account_validation
                headers = {
                    "Authorization": razorpay_key_secret_auth,
                    "content-type": "application/json",
                }
                raw_res = requests.post(
                    url=url,
                    headers=headers,
                    data=json.dumps(data_rzp),
                )

                data_res = raw_res.json()
                log = {
                    "url": las_settings.pennydrop_create_fund_account_validation,
                    "headers": headers,
                    "request": data_rzp,
                    "response": data_res,
                }

                create_log(log, "rzp_pennydrop_create_fund_account_validation")

            penny_handle = penny_api_response_handle(
                data,
                user_kyc,
                customer,
                data_res,
                personalized_cheque=personalized_cheque,
            )
            return penny_handle
        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))

    except utils.exceptions.APIException as e:
        log_api_error()
        frappe.log_error(
            title="Penny Drop Create fund account validation Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create fund account validation Error: "
            + str(e.args),
        )
        return e.respond()


def call_penny_create_fund_account_validation_by_id(
    user=None,
    fav_id=None,
    personalized_cheque=None,
):
    try:
        # utils.validator.validate_http_method("POST")
        # data = utils.validator.validate(
        #     kwargs,
        #     {
        #         "fav_id": "required",
        #         "personalized_cheque": "required",
        #     },
        # )
        # check user
        # try:
        #     user = lms.__user()
        # except UserNotFoundException:
        #     # return utils.respondNotFound(message=frappe._("User not found."))
        #     raise lms.exceptions.NotFoundException(_("User not found"))

        try:
            user_name = user
            if not user:
                user = __user()
                user_name = user.name
        except UserNotFoundException:
            # return utils.respondNotFound(message=frappe._("User not found."))
            data = {"message": "User not found"}
            return data

        # check Loan Customer
        customer = __customer(user_name)
        if not customer:
            # return utils.respondNotFound(message=frappe._("Customer not found."))
            # raise exceptions.NotFoundException(_("Customer not found"))
            data = {"message": "Customer not found"}
            return data

        # user KYC
        try:
            user_kyc = __user_kyc(user_name)
        except UserKYCNotFoundException:
            # return utils.respondWithFailure(message=frappe._("User KYC not found"))
            # raise exceptions.RespondWithFailureException(_("User KYC not found"))
            data = {"message": "User KYC not found"}
            return data

        # fetch rzp key secret from las settings and use Basic auth
        las_settings = frappe.get_single("LAS Settings")
        if not las_settings.razorpay_key_secret:
            frappe.log_error(
                title="Penny Drop Fund Account Validation Error",
                message="Penny Drop Fund Account Validation Error - Razorpay Key Secret Missing",
            )
            # return utils.respondWithFailure()
            # raise exceptions.RespondWithFailureException()
            data = {
                "message": "Penny Drop Fund Account Validation Error - Razorpay Key Secret Missing"
            }
            return data

        razorpay_key_secret_auth = "Basic " + base64.b64encode(
            bytes(las_settings.razorpay_key_secret, "utf-8")
        ).decode("ascii")

        try:
            data = {
                "fav_id": fav_id,
            }
            if "rzp_test_" in las_settings.razorpay_key_secret:
                data_res = {
                    "id": "fav_JpHg4DC2VJ80Zw",
                    "entity": "fund_account.validation",
                    "fund_account": {
                        "id": "fa_KO3f6cc2X8oLW7",
                        "entity": "fund_account",
                        "contact_id": "cont_JpHHIYu00BTzNL",
                        "account_type": "bank_account",
                        "bank_account": {
                            "ifsc": "ICIC0000004",
                            "bank_name": "ICICI Bank",
                            "name": "Choice Finserv private limited",
                            "notes": [],
                            "account_number": "000405112506",
                        },
                        "batch_id": None,
                        "active": True,
                        "created_at": 1656935250,
                        "details": {
                            "ifsc": "ICIC0000004",
                            "bank_name": "ICICI Bank",
                            "name": "Choice Finserv private limited",
                            "notes": [],
                            "account_number": "000405112506",
                        },
                    },
                    "status": "completed",
                    "amount": 100,
                    "currency": "INR",
                    "notes": {
                        # "branch": data.get("branch"),
                        # "city": data.get("city"),
                        # "bank_account_type": data.get("bank_account_type"),
                    },
                    "results": {
                        "account_status": "active",
                        "registered_name": user_kyc.fname,
                    },
                    "created_at": 1656936646,
                    "utr": None,
                }
            else:
                url = (
                    las_settings.pennydrop_create_fund_account_validation_id
                    + "/{}".format(data.get("fav_id"))
                )
                headers = {
                    "Authorization": razorpay_key_secret_auth,
                    "content-type": "application/json",
                }
                raw_res = requests.get(
                    url=url,
                    headers=headers,
                )

                data_res = raw_res.json()
                log = {
                    "url": url,
                    "headers": headers,
                    "request": data,
                    "response": data_res,
                }

                # create_log(log, "rzp_pennydrop_create_fund_account_validation_by_id")
            validation_by_id = penny_api_response_handle(
                data,
                user_kyc,
                customer,
                data_res,
                personalized_cheque=personalized_cheque,
            )
            return validation_by_id

        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))

    except utils.exceptions.APIException as e:
        log_api_error()
        frappe.log_error(
            title="Penny Drop Create fund account validation Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create fund account validation Error: "
            + str(e.args),
        )
        return e.respond()


def penny_api_response_handle(
    data, user_kyc, customer, data_res, personalized_cheque=None
):
    try:
        data_resp = {
            "fav_id": data_res.get("id"),
            "status": data_res.get("status"),
        }
        if data_res.get("error"):
            data_resp["status"] = "failed"
            message = "Your account details have not been successfully verified"
            log = {
                "request": data,
                "response": data_res,
            }
            create_log(log, "rzp_penny_fund_account_validation_error_log")
            # raise utils.respondWithFailure(message=message)
            # raise exceptions.RespondWithFailureException(message=message)
            data = {
                "message": "Your account details have not been successfully verified"
            }
            return data

        if data_res.get("status") == "failed":
            data = {
                "message": "Your account details have not been successfully verified"
            }
            return data
            # return utils.respondWithFailuremessage=message, data=data_resp)
            # raise exceptions.RespondFailureException(message, data_resp)

        if data_res.get("status") == "created":
            data = {"message": "waiting for response from bank"}
            return data

        account_status = data_res.get("results").get("account_status")
        if data_res.get("status") == "completed" and account_status == "active":
            # name validation - check user entered account holder name is same with registered name
            # account_holder_name = (
            #     data_res.get("fund_account")
            #     .get("bank_account")
            #     .get("name")
            #     .lower()
            #     .split(" ")
            # )
            registered_name = data_res.get("results").get("registered_name").lower()
            account_status = data_res.get("results").get("account_status")
            photos_ = personalized_cheque
            if personalized_cheque:
                photos_ = upload_image_to_doctype(
                    customer=customer,
                    seq_no=data_res.get("fund_account")
                    .get("bank_account")
                    .get("account_number")[-4:],
                    image_=personalized_cheque,
                    img_format="jpeg",
                    img_folder="personalized_cheque",
                )

            if user_kyc.fname.lower() in registered_name:

                message = "Your account details have been successfully verified"

                # check bank Entry existence. if not exist then create entry
                if user_kyc.kyc_type == "CHOICE":
                    bank_entry_name = frappe.db.get_value(
                        "User Bank Account",
                        {
                            "parentfield": "bank_account",
                            # "razorpay_fund_account_id": data_res.get(
                            #     "fund_account"
                            # ).get("id"),
                            "account_number": data_res.get("fund_account")
                            .get("bank_account")
                            .get("account_number"),
                        },
                        "name",
                    )

                    if not bank_entry_name:
                        bank_account_list = frappe.get_all(
                            "User Bank Account",
                            filters={"parent": user_kyc.name},
                            fields="*",
                        )
                        for b in bank_account_list:
                            if bank_entry_name != b.name:
                                other_bank = frappe.get_doc("User Bank Account", b.name)
                                if other_bank.is_default == 1:
                                    other_bank.is_default = 0
                                    other_bank.save(ignore_permissions=True)
                        frappe.get_doc(
                            {
                                "doctype": "User Bank Account",
                                "parentfield": "bank_account",
                                "parenttype": "User KYC",
                                "bank": data_res.get("fund_account")
                                .get("bank_account")
                                .get("bank_name"),
                                "branch": data_res.get("notes").get("branch"),
                                "account_type": data_res.get("notes").get(
                                    "bank_account_type"
                                ),
                                "account_number": data_res.get("fund_account")
                                .get("bank_account")
                                .get("account_number"),
                                "ifsc": data_res.get("fund_account")
                                .get("bank_account")
                                .get("ifsc"),
                                "account_holder_name": data_res.get("fund_account")
                                .get("bank_account")
                                .get("name"),
                                "personalized_cheque": photos_,
                                "city": data_res.get("notes").get("city"),
                                "parent": user_kyc.name,
                                "is_default": True,
                                "razorpay_fund_account_id": data_res.get(
                                    "fund_account"
                                ).get("id"),
                                "razorpay_fund_account_validation_id": data_res.get(
                                    "id"
                                ),
                                "bank_status": "Pending",
                            }
                        ).insert(ignore_permissions=True)
                        # frappe.db.commit()
                    else:
                        # For existing choice bank entries
                        bank_account = frappe.get_doc(
                            "User Bank Account", bank_entry_name
                        )
                        bank_account.account_holder_name = (
                            data_res.get("fund_account").get("bank_account").get("name")
                        )
                        bank_account.razorpay_fund_account_id = (
                            (data_res.get("fund_account").get("id")),
                        )
                        bank_account.razorpay_fund_account_validation_id = (
                            data_res.get("id"),
                        )
                        bank_account.personalized_cheque = photos_
                        bank_account.bank_status = "Pending"
                        bank_account.save(ignore_permissions=True)
                        frappe.db.commit()
                else:
                    # For non choice user
                    frappe.get_doc(
                        {
                            "doctype": "User Bank Account",
                            "parentfield": "bank_account",
                            "parenttype": "User KYC",
                            "bank": data_res.get("fund_account")
                            .get("bank_account")
                            .get("bank_name"),
                            "branch": data_res.get("notes").get("branch"),
                            "account_type": data_res.get("notes").get(
                                "bank_account_type"
                            ),
                            "account_number": data_res.get("fund_account")
                            .get("bank_account")
                            .get("account_number"),
                            "ifsc": data_res.get("fund_account")
                            .get("bank_account")
                            .get("ifsc"),
                            "account_holder_name": data_res.get("fund_account")
                            .get("bank_account")
                            .get("name"),
                            "personalized_cheque": photos_,
                            "city": data_res.get("notes").get("city"),
                            "parent": user_kyc.name,
                            "is_default": True,
                            "razorpay_fund_account_id": data_res.get(
                                "fund_account"
                            ).get("id"),
                            "razorpay_fund_account_validation_id": data_res.get("id"),
                            "bank_status": "Pending",
                        }
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
            else:
                data_resp["status"] = "failed"
                data = {
                    "data_resp": data_resp,
                    "message": "We have found a mismatch in the account holder name as per the fetched data",
                }
                return data
        else:
            data_resp["status"] = "failed"
            data = {
                "data_resp": data_resp,
                "message": "Your account details have not been successfully verified",
            }
            return data

        create_log(data_res, "rzp_penny_fund_account_validation_success_log")
        return data_res
    except utils.exceptions.APIException as e:
        log_api_error(
            str(message if message else "")
            + "\n"
            + str(data_resp if data_resp else data_res)
        )
        return e.respond()


@frappe.whitelist(allow_guest=True)
def penny_validate_fund_account():
    try:
        log = {
            "request": frappe.local.form_dict,
            "headers": {k: v for k, v in frappe.local.request.headers.items()},
        }
        create_log(log, "penny_validate_fund_account")
        return log

    except Exception:
        log_api_error()


def au_pennydrop_api(data, kyc_full_name):
    try:
        ReqId = datetime.strftime(datetime.now(), "%d%m") + str(
            abs(randint(0, 9999) - randint(1, 99))
        )
        las_settings = frappe.get_single("LAS Settings")
        SECRET_KEY = las_settings.penny_secret_key

        # ReqId + IFSCCode + AccNum

        hash_text = "{}{}{}".format(ReqId, data.get("ifsc"), data.get("account_number"))

        final_hash = hmac.new(
            key=bytes(SECRET_KEY, "utf-8"),
            msg=bytes(hash_text, "utf-8"),
            digestmod="sha512",
        ).digest()

        payload = {
            "ReqId": ReqId,
            "IFSCCode": data.get("ifsc"),
            "AccNum": data.get("account_number"),
            "BeneficiaryName": kyc_full_name,
            "HashValue": base64.b64encode(final_hash).decode("ascii"),
        }
        data["payload"] = payload

        url = las_settings.penny_drop_api
        if not url:
            res_json = {"StatusCode": 404, "Message": "Penny Drop host missing"}
            return res_json

        headers = {
            "Content-Type": "application/json",
        }
        res = requests.post(url=url, json=payload, headers=headers)

        res_json = res.json()

        create_log(
            {"url": url, "headers": headers, "request": payload, "response": res_json},
            "au_penny_drop",
        )
        return res_json
    except Exception:
        frappe.log_error(
            title="AU Penny Drop API Error",
            message=frappe.get_traceback() + "\n\n" + str(data),
        )


def truncate_float_to_decimals(number, digits):
    return math.floor(number * 10 ** digits) / 10 ** digits


def name_matching(user_kyc, bank_acc_full_name):
    try:
        bank_acc_full_name = bank_acc_full_name.lower().replace(" ", "")

        if (
            user_kyc.fname
            and user_kyc.fname.replace(" ", "").lower() in bank_acc_full_name
        ) and (
            user_kyc.mname
            and user_kyc.mname.replace(" ", "").lower() in bank_acc_full_name
        ):
            return True
        elif (
            user_kyc.fname
            and user_kyc.fname.replace(" ", "").lower() in bank_acc_full_name
        ) and (
            user_kyc.lname
            and user_kyc.lname.replace(" ", "").lower() in bank_acc_full_name
        ):
            return True
        elif (user_kyc.fname and not user_kyc.mname and not user_kyc.lname) and (
            user_kyc.fname.replace(" ", "").lower() in bank_acc_full_name
        ):
            return True
        else:
            return False
    except Exception:
        frappe.log_error(
            title="Name matching Error",
            message=frappe.get_traceback()
            + "User Kyc Name:\n{}\n\n".format(user_kyc.name),
        )


def calculate_apr(name_, interest_in_percentage, tenure, sanction_limit, charges=0):
    try:
        pmt_ = npf.pmt((interest_in_percentage / 100) / 12, tenure, sanction_limit)
        present_value = sanction_limit - charges
        future_value = 0
        apr = (
            npf.rate(nper=tenure, pmt=pmt_, pv=present_value, fv=future_value)
            * 12
            * 100
        )
        if apr < 0:
            apr = 0

        return round(apr, 2)
    except Exception:
        frappe.log_error(
            title="Calculate APR Error",
            message=frappe.get_traceback() + "\n\n" + str(name_),
        )


def diff_in_months(date_1, date_2):
    start = datetime.strptime(date_1, "%d/%m/%Y")
    end = datetime.strptime(date_2, "%d/%m/%Y")
    diff = (end.year - start.year) * 12 + (end.month - start.month)
    return diff


def validate_loan_charges_amount(lender_doc, amount, min_field, max_field):
    lender_dict = lender_doc.as_dict()
    if (lender_dict[min_field] > 0) and (amount < lender_dict[min_field]):
        amount = lender_dict[min_field]
    elif (lender_dict[max_field] > 0) and (amount > lender_dict[max_field]):
        amount = lender_dict[max_field]
    return amount


def charges_for_apr(lender, sanction_limit):
    charges = {}
    lender = frappe.get_doc("Lender", lender)
    date = frappe.utils.now_datetime()
    days_in_year = 366 if calendar.isleap(date.year) else 365
    processing_fees = lender.lender_processing_fees
    if lender.lender_processing_fees_type == "Percentage":
        days_left_to_expiry = days_in_year
        amount = (
            (processing_fees / 100)
            * sanction_limit
            / days_in_year
            * days_left_to_expiry
        )
        processing_fees = validate_loan_charges_amount(
            lender,
            amount,
            "lender_processing_minimum_amount",
            "lender_processing_maximum_amount",
        )
    charges["processing_fees"] = processing_fees

    # Stamp Duty
    stamp_duty = lender.stamp_duty
    if lender.stamp_duty_type == "Percentage":
        amount = (stamp_duty / 100) * sanction_limit
        stamp_duty = validate_loan_charges_amount(
            lender,
            amount,
            "lender_stamp_duty_minimum_amount",
            "lender_stamp_duty_maximum_amount",
        )
    charges["stamp_duty"] = stamp_duty

    documentation_charges = lender.documentation_charges
    if lender.documentation_charge_type == "Percentage":
        amount = (documentation_charges / 100) * sanction_limit
        documentation_charges = validate_loan_charges_amount(
            lender,
            amount,
            "lender_documentation_minimum_amount",
            "lender_documentation_maximum_amount",
        )
    charges["documentation_charges"] = documentation_charges
    total = processing_fees + stamp_duty + documentation_charges
    charges["total"] = total
    return charges


def compress_image(input_image_path, user, quality=100):
    try:
        original_image = Image.open(input_image_path)
        if (
            10 > os.path.getsize(input_image_path) / 1048576 > 1
        ):  # size of image in mb(bytes/(1024*1024))
            quality = 50
        original_image.save(input_image_path, quality=quality)
        return input_image_path
    except Exception:
        frappe.log_error(
            title="Compress Image Error",
            message=frappe.get_traceback()
            + "User Name:\n{}\nFile Path:\n{}".format(user, input_image_path),
        )


def pdf_editor(esigned_doc, loan_application_name, loan_name=None):
    registerFont(TTFont("Calibri-Bold", "calibrib.ttf"))

    lfile_name = esigned_doc.split("files/", 1)
    l_file = lfile_name[1]
    pdf_file_path = frappe.utils.get_files_path(
        l_file,
    )
    # read your existing PDF
    pdf_path = pdf_file_path  # for u its ur original pdf
    existing_pdf = PdfReader(open(pdf_file_path, "rb"))
    reader = PdfReader(pdf_path)
    num_of_page = len(existing_pdf.pages)
    output = PdfWriter()
    for i in range(30):
        page = reader.pages[i]
        output.add_page(page)

    current_time = frappe.utils.now_datetime().strftime("%d-%m-%Y")
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Calibri-Bold", 10)
    can.drawString(80, 765, current_time)
    if loan_name:
        can.drawString(89, 753, loan_name)
    can.save()
    packet.seek(0)
    watermark = PdfReader(packet).pages[0]
    page21 = reader.pages[30]
    page21.merge_page(watermark)
    output.add_page(page21)

    for i in range(31, 36):
        page = reader.pages[i]
        output.add_page(page)

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Calibri-Bold", 10)
    if loan_name:
        can.drawString(118, 767, current_time)
    else:
        can.drawString(118, 767, current_time)
    can.save()
    packet.seek(0)
    watermark = PdfReader(packet).pages[0]
    page25 = reader.pages[36]
    page25.merge_page(watermark)
    output.add_page(page25)

    for i in range(37, num_of_page):
        page = reader.pages[i]
        output.add_page(page)
    # finally, write "output" to a real file
    sanction_letter_esign = "{}_{}.pdf".format(
        loan_application_name, frappe.utils.now_datetime().strftime("%Y-%m-%d")
    )
    sanction_letter_esign_path = frappe.utils.get_files_path(sanction_letter_esign)
    sanction_letter_esign_doc = frappe.utils.get_url(
        "files/{}".format(sanction_letter_esign)
    )
    if os.path.exists(sanction_letter_esign_path):
        os.remove(sanction_letter_esign_path)

    sanction_letter_esign = frappe.utils.get_files_path(sanction_letter_esign)
    output_stream = open(sanction_letter_esign, "wb")
    output.write(output_stream)
    output_stream.close()
    return sanction_letter_esign_doc


PDF_CONTENT_ERRORS = [
    "ContentNotFoundError",
    "ContentOperationNotPermittedError",
    "UnknownContentError",
    "RemoteHostClosedError",
]


def get_pdf(html, options=None, output=None):
    html = scrub_urls(html)
    html, options = prepare_options(html, options)

    options.update({"disable-javascript": "", "disable-local-file-access": ""})

    filedata = ""
    if LooseVersion(get_wkhtmltopdf_version()) > LooseVersion("0.12.3"):
        options.update({"disable-smart-shrinking": ""})

    try:
        # Set filename property to false, so no file is actually created
        filedata = pdfkit.from_string(html, False, options=options or {})

        # https://pythonhosted.org/PyPDF2/PdfFileReader.html
        # create in-memory binary streams from filedata and create a PdfFileReader object
        reader = PdfReader(io.BytesIO(filedata))
    except OSError as e:
        if any([error in str(e) for error in PDF_CONTENT_ERRORS]):
            if not filedata:
                frappe.throw(_("PDF generation failed because of broken image links"))

            # allow pdfs with missing images if file got created
            if output:  # output is a PdfFileWriter object
                output.append_pages_from_reader(reader)
        else:
            raise
    finally:
        cleanup(options)

    if "password" in options:
        password = options["password"]
        if six.PY2:
            password = frappe.safe_encode(password)

    if output:
        output.append_pages_from_reader(reader)
        return output

    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    if "password" in options:
        writer.encrypt(password)

    filedata = get_file_data_from_writer(writer)

    return filedata


def get_file_data_from_writer(writer_obj):

    # https://docs.python.org/3/library/io.html
    stream = io.BytesIO()
    writer_obj.write(stream)

    # Change the stream position to start of the stream
    stream.seek(0)

    # Read up to size bytes from the object and return them
    return stream.read()


def prepare_options(html, options):
    if not options:
        options = {}

    options.update(
        {
            "print-media-type": None,
            "background": None,
            "images": None,
            "quiet": None,
            # 'no-outline': None,
            "encoding": "UTF-8",
            #'load-error-handling': 'ignore'
        }
    )

    if not options.get("margin-right"):
        options["margin-right"] = "15mm"

    if not options.get("margin-left"):
        options["margin-left"] = "15mm"

    html, html_options = read_options_from_html(html)
    options.update(html_options or {})

    # cookies
    options.update(get_cookie_options())

    # page size
    if not options.get("page-size"):
        options["page-size"] = (
            frappe.db.get_single_value("Print Settings", "pdf_page_size") or "A4"
        )

    return html, options


def get_wkhtmltopdf_version():
    wkhtmltopdf_version = frappe.cache().hget("wkhtmltopdf_version", None)

    if not wkhtmltopdf_version:
        try:
            res = subprocess.check_output(["wkhtmltopdf", "--version"])
            wkhtmltopdf_version = res.decode("utf-8").split(" ")[1]
            frappe.cache().hset("wkhtmltopdf_version", None, wkhtmltopdf_version)
        except Exception:
            pass

    return wkhtmltopdf_version or "0"


def cleanup(options):
    for key in ("header-html", "footer-html", "cookie-jar"):
        if options.get(key) and os.path.exists(options[key]):
            os.remove(options[key])


def read_options_from_html(html):
    options = {}
    soup = BeautifulSoup(html, "html5lib")

    options.update(prepare_header_footer(soup))

    toggle_visible_pdf(soup)

    # use regex instead of soup-parser
    for attr in (
        "margin-top",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "page-size",
        "header-spacing",
        "orientation",
    ):
        try:
            pattern = re.compile(
                r"(\.print-format)([\S|\s][^}]*?)(" + str(attr) + r":)(.+)(mm;)"
            )
            match = pattern.findall(html)
            if match:
                options[attr] = str(match[-1][3]).strip()
        except:
            pass

    return str(soup), options


def get_cookie_options():
    options = {}
    if frappe.session and frappe.session.sid and hasattr(frappe.local, "request"):
        # Use wkhtmltopdf's cookie-jar feature to set cookies and restrict them to host domain
        cookiejar = "/tmp/{}.jar".format(frappe.generate_hash())

        # Remove port from request.host
        # https://werkzeug.palletsprojects.com/en/0.16.x/wrappers/#werkzeug.wrappers.BaseRequest.host
        domain = frappe.utils.get_host_name().split(":", 1)[0]
        with open(cookiejar, "w") as f:
            f.write("sid={}; Domain={};\n".format(frappe.session.sid, domain))

        options["cookie-jar"] = cookiejar

    return options


def prepare_header_footer(soup):
    options = {}

    head = soup.find("head").contents
    styles = soup.find_all("style")

    css = frappe.read_file(
        os.path.join(frappe.local.sites_path, "assets/css/printview.css")
    )

    # extract header and footer
    for html_id in ("header-html", "footer-html"):
        content = soup.find(id=html_id)
        if content:
            # there could be multiple instances of header-html/footer-html
            for tag in soup.find_all(id=html_id):
                tag.extract()

            toggle_visible_pdf(content)
            html = frappe.render_template(
                "templates/print_formats/pdf_header_footer.html",
                {
                    "head": head,
                    "content": content,
                    "styles": styles,
                    "html_id": html_id,
                    "css": css,
                },
            )

            # create temp file
            fname = os.path.join(
                "/tmp", "frappe-pdf-{0}.html".format(frappe.generate_hash())
            )
            with open(fname, "wb") as f:
                f.write(html.encode("utf-8"))

            # {"header-html": "/tmp/frappe-pdf-random.html"}
            options[html_id] = fname
        else:
            if html_id == "header-html":
                options["margin-top"] = "15mm"
            elif html_id == "footer-html":
                options["margin-bottom"] = "15mm"

    return options


def toggle_visible_pdf(soup):
    for tag in soup.find_all(attrs={"class": "visible-pdf"}):
        # remove visible-pdf class to unhide
        tag.attrs["class"].remove("visible-pdf")

    for tag in soup.find_all(attrs={"class": "hidden-pdf"}):
        # remove tag from html
        tag.extract()


def personalized_cheque_log(name, image_, img_format):
    try:
        name = name + "_" + str(frappe.utils.now_datetime())

        picture_file = "{}.{}".format(name, img_format).replace(" ", "-")

        image_path = frappe.utils.get_files_path(picture_file)
        if os.path.exists(image_path):
            os.remove(image_path)

        ckyc_image_file_path = frappe.utils.get_files_path(picture_file)
        image_decode = base64.decodestring(bytes(str(image_), encoding="utf8"))
        image_file = open(ckyc_image_file_path, "wb").write(image_decode)

        ckyc_image_file_url = frappe.utils.get_url(
            "files/{}.{}".format(name, img_format).replace(" ", "-")
        )
        create_log({"url": ckyc_image_file_url}, "personalized_cheque_log")

        return ckyc_image_file_url
    except Exception:
        frappe.log_error(
            title="Personalized cheque Error",
            message=frappe.get_traceback() + "\n\nUser:{}".format(frappe.session.user),
        )
