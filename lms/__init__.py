# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import hmac
import json
import os
import re
from datetime import datetime, timedelta
from inspect import currentframe
from itertools import groupby
from random import choice, randint
from traceback import format_exc

import frappe
import razorpay
import requests
import utils
from frappe import _
from razorpay.errors import SignatureVerificationError

from lms.config import lms
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.user_token.user_token import send_sms

from .exceptions import *

# from lms.exceptions.CustomerNotFoundException import CustomerNotFoundException
# from lms.exceptions.InvalidUserTokenException import InvalidUserTokenException
# from lms.exceptions.UserKYCNotFoundException import UserKYCNotFoundException

# from lms.exceptions.UserNotFoundException import UserNotFoundException

__version__ = "3.2.0"

user_token_expiry_map = {
    "OTP": 10,
    # "Email Verification Token": 60,
    "Pledge OTP": 10,
    "Withdraw OTP": 10,
    "Unpledge OTP": 10,
    "Sell Collateral OTP": 10,
    "Forgot Pin OTP": 10,
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
    # print("get_user", frappe.as_json(user_data))
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


def get_security_categories(securities, lender):
    query = """select isin, category from `tabAllowed Security`
				where
				lender = '{}' and
				isin in {}""".format(
        lender, convert_list_to_tuple_string(securities)
    )

    results = frappe.db.sql(query, as_dict=1)

    security_map = {}

    for r in results:
        security_map[r.isin] = r.category

    return security_map


def get_allowed_securities(securities, lender):
    query = """select
				isin, security_name, eligible_percentage, security_category
				from `tabAllowed Security`
				where
				lender = '{}' and
				isin in {}""".format(
        lender, convert_list_to_tuple_string(securities)
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
    filters = {"user": __user(entity).name}
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

    for i in res:
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


def add_firebase_token(firebase_token, user=None):
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

    create_user_token(entity=user, token=firebase_token, token_type="Firebase Token")


def create_user_token(entity, token, token_type="OTP"):
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
                res = requests.post(
                    url="https://fcm.googleapis.com/fcm/send",
                    data=json.dumps(fcm_payload),
                    headers=headers,
                )

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
        webhook_signature = headers.get("X-Razorpay-Signature")
        log = {"rzp_payment_webhook_response": data, "headers": headers}
        create_log(log, "rzp_payment_webhook_log")

        expected_signature = hmac.new(
            digestmod="sha256",
            msg=frappe.local.request.data,
            key=bytes(webhook_secret, "utf-8"),
        )
        generated_signature = expected_signature.hexdigest()
        result = hmac.compare_digest(generated_signature, webhook_signature)
        if not result:
            raise SignatureVerificationError("Razorpay Signature Verification Failed")

        # Assign RZP user session for updating loan transaction
        if rzp_user and result:
            frappe.session.user = rzp_user[0]["name"]

            if (
                data
                and len(data) > 0
                and data["entity"] == "event"
                and data["event"]
                in ["payment.authorized", "payment.captured", "payment.failed"]
            ):
                frappe.enqueue(
                    method="lms.update_rzp_payment_transaction",
                    data=data,
                    job_name="Payment Webhook",
                )
        if not rzp_user:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nWebhook details:\n"
                + json.dumps(data),
                title=_("Payment Webhook RZP User not found Error"),
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
            if data["event"] == "payment.authorized":
                razorpay_event = "Authorized"
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
            if data["event"] == "payment.authorized":
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
                receiver_list = list(
                    set([str(customer.phone), str(customer.get_kyc().mobile_number)])
                )

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


def split_list_into_half(a_list):
    half = len(a_list) // 2
    return a_list[:half], a_list[half:]


def get_linenumber():
    cf = currentframe()
    return "line no" + str(cf.f_back.f_lineno)
