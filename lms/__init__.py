# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import os
import re
from datetime import datetime, timedelta
from itertools import groupby
from random import choice, randint
from traceback import format_exc

import frappe
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms

from lms.config import lms
from lms.firebase import FirebaseAdmin

from .exceptions import *

# from lms.exceptions.CustomerNotFoundException import CustomerNotFoundException
# from lms.exceptions.InvalidUserTokenException import InvalidUserTokenException
# from lms.exceptions.UserKYCNotFoundException import UserKYCNotFoundException

# from lms.exceptions.UserNotFoundException import UserNotFoundException

__version__ = "1.1.0"

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
        "User Bank Account", filters={"parent": user_kyc}, fields=["*"]
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


def send_spark_push_notification(
    fcm_notification={}, message="", loan="", customer=None
):
    if fcm_notification:
        if message:
            message = message
        else:
            message = fcm_notification.message

        try:
            fa = FirebaseAdmin()
            random_id = randint(1, 2147483646)
            current_time = frappe.utils.now_datetime()
            notification_name = (str(random_id) + " " + str(current_time)).replace(
                " ", "-"
            )

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

            fa.send_android_message(
                title=fcm_notification.title,
                body=message,
                data=data,
                tokens=get_firebase_tokens(customer.user),
                priority="high",
            )
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
        except Exception as e:
            # return e
            # To log fcm notification exception errors into Frappe Error Log
            frappe.log_error(
                frappe.get_traceback() + "\nNotification Info:\n" + json.dumps(data),
                e.args,
            )
        finally:
            fa.delete_app()


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
