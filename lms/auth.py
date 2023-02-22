import json
import re
import webbrowser
from datetime import datetime, timedelta

import frappe
import utils
from frappe import _

# from frappe.auth import LoginManager, get_login_failed_count
from frappe.auth import LoginAttemptTracker, get_login_attempt_tracker
from frappe.utils.password import (
    check_password,
    delete_login_failed_cache,
    update_password,
)

import lms

# from lms.exceptions.InvalidUserTokenException import InvalidUserTokenException
# from lms.exceptions.UserKYCNotFoundException import UserKYCNotFoundException
# from lms.exceptions.UserNotFoundException import UserNotFoundException
from lms.exceptions import *
from lms.lms.doctype.user_token.user_token import send_sms


@frappe.whitelist(allow_guest=True)
def login(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "mobile": ["required", "decimal", utils.validator.rules.LengthRule(10)],
                "pin": [utils.validator.rules.LengthRule(4)],
                "firebase_token": [utils.validator.rules.RequiredIfPresent("pin")],
                "accept_terms": "decimal|between:0,1",
                "platform": "",
                "app_version": "",
            },
        )
        if data.get("firebase_token"):
            # for firebase token "-_:" these characters are excluded from regex string
            reg = lms.regex_special_characters(
                search=data.get("firebase_token"),
                regex=re.compile("[@!#$%^&*()<>?/\|}{~`]"),
            )
            if reg:
                # return utils.respondWithFailure(
                #     status=422,
                #     message=frappe._("Special Characters not allowed."),
                # )
                raise lms.exceptions.FailureException(
                    _("Special Characters not allowed.")
                )

        try:
            user = lms.__user(data.get("mobile"))
        except UserNotFoundException:
            user = None

        # frappe.db.begin()
        if data.get("pin"):
            try:
                frappe.local.login_manager.authenticate(
                    user=user.name, pwd=data.get("pin")
                )
            except frappe.SecurityException as e:
                # raise utils.respondUnauthorized(message=str(e))
                raise lms.exceptions.UnauthorizedException(str(e))
            except frappe.AuthenticationError as e:
                message = frappe._("Incorrect PIN.")
                invalid_login_attempts = get_login_attempt_tracker(user.name)
                if invalid_login_attempts.login_failed_count > 0:
                    message += " {} invalid {}.".format(
                        invalid_login_attempts.login_failed_count,
                        "attempt"
                        if invalid_login_attempts.login_failed_count == 1
                        else "attempts",
                    )
                # return utils.respondUnauthorized(message=message)
                raise lms.exceptions.UnauthorizedException(message)

            customer = lms.__customer(user.name)
            try:
                user_kyc = lms.__user_kyc(user.name)
            except UserKYCNotFoundException:
                user_kyc = {}

            if user_kyc:
                user_kyc = lms.user_kyc_hashing(user_kyc)

            token = dict(
                token=utils.create_user_access_token(user.name),
                customer=customer,
                user_kyc=user_kyc,
            )
            app_version_platform = ""
            if data.get("app_version") and data.get("platform"):
                app_version_platform = (
                    data.get("app_version") + " | " + data.get("platform")
                )
            lms.add_firebase_token(
                data.get("firebase_token"), app_version_platform, user.name
            )
            lms.auth.login_activity(customer)
            return utils.respondWithSuccess(
                message=frappe._("Logged in Successfully"), data=token
            )
        else:
            if not data.get("accept_terms"):
                # return utils.respondUnauthorized(
                #     message=frappe._("Please accept Terms of Use and Privacy Policy.")
                # )
                raise lms.exceptions.UnauthorizedException(
                    _("Please accept Terms of Use and Privacy Policy.")
                )

            # save user login consent
            login_consent_doc = frappe.get_doc(
                {
                    "doctype": "User Consent",
                    "mobile": data.get("mobile"),
                    "consent": "Login",
                }
            )
            login_consent_doc.insert(ignore_permissions=True)

        # check if dummy account
        is_dummy_account = lms.validate_spark_dummy_account(data.get("mobile"))

        if not is_dummy_account:
            lms.create_user_token(
                entity=data.get("mobile"),
                token=lms.random_token(length=4, is_numeric=True),
            )

        frappe.db.commit()
        return utils.respondWithSuccess(message=frappe._("OTP Sent"))
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()
    except frappe.SecurityException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return utils.respondUnauthorized(message=str(e))
        # raise lms.exceptions.UnauthorizedException(str(e))


@frappe.whitelist()
def logout(firebase_token):
    get_user_token = frappe.db.get_value(
        "User Token", {"token_type": "Firebase Token", "token": firebase_token}
    )
    # print(get_user_token)
    if not get_user_token:
        raise lms.ValidationError(_("Firebase Token does not exist."))
    else:
        frappe.db.set_value("User Token", get_user_token, "used", 1)
        # filters = {'name': frappe.session.user}
        frappe.db.sql(
            """ delete from `__Auth` where doctype='User' and name='{}' and fieldname='api_secret' """.format(
                frappe.session.user
            )
        )
        frappe.local.login_manager.logout()
        frappe.db.commit()
        return lms.generateResponse(message=_("Logged out Successfully"))


@frappe.whitelist(allow_guest=True)
def terms_of_use():
    try:
        # validation
        lms.validate_http_method("GET")

        las_settings = frappe.get_single("LAS Settings")
        data = {
            "terms_of_use_url": frappe.utils.get_url(las_settings.terms_of_use_document)
            or "",
            "privacy_policy_url": frappe.utils.get_url(
                las_settings.privacy_policy_document
            )
            or "",
            "dummy_accounts": frappe.get_list("Spark Dummy Account", pluck="mobile"),
        }
        return utils.respondWithSuccess(message=frappe._("success"), data=data)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist(allow_guest=True)
def verify_otp(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "mobile": ["required", "decimal", utils.validator.rules.LengthRule(10)],
                "firebase_token": "required",
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
                "platform": "",
                "app_version": "",
            },
        )
        if data.get("firebase_token"):
            # for firebase token "-_:" these characters are excluded from regex string
            reg = lms.regex_special_characters(
                search=data.get("firebase_token"),
                regex=re.compile("[@!#$%^&*()<>?/\|}{~`]"),
            )
            if reg:
                # return utils.respondWithFailure(
                #     status=422,
                #     message=frappe._("Special Characters not allowed."),
                # )
                raise lms.exceptions.FailureException(
                    _("Special Characters not allowed.")
                )

        try:
            is_dummy_account = lms.validate_spark_dummy_account(data.get("mobile"))
            if not is_dummy_account:
                token = lms.verify_user_token(
                    entity=data.get("mobile"), token=data.get("otp"), token_type="OTP"
                )
            else:
                token = lms.validate_spark_dummy_account_token(
                    data.get("mobile"), data.get("otp")
                )
        except InvalidUserTokenException:
            token = None

        try:
            user = lms.__user(data.get("mobile"))
        except UserNotFoundException:
            user = None

        if not token:
            message = frappe._("Invalid OTP.")
            if user:
                # frappe.local.login_manager.update_invalid_login(user.name)
                # try:
                #     frappe.local.login_manager.check_if_enabled(user.name)
                # except frappe.SecurityException as e:
                #     return utils.respondUnauthorized(message=str(e))
                LoginAttemptTracker(user_name=user.name).add_failure_attempt()
                if not user.enabled:
                    # return utils.respondUnauthorized(message="User disabled or missing")
                    raise lms.exceptions.UnauthorizedException(
                        _("User disabled or missing")
                    )

                invalid_login_attempts = get_login_attempt_tracker(user.name)
                if invalid_login_attempts.login_failed_count > 0:
                    message += " {} invalid {}.".format(
                        invalid_login_attempts.login_failed_count,
                        "attempt"
                        if invalid_login_attempts.login_failed_count == 1
                        else "attempts",
                    )

            # return utils.respondUnauthorized(message=message)
            raise lms.exceptions.UnauthorizedException(message)

        if token:
            # frappe.db.begin()
            if (not is_dummy_account) and (token.expiry <= frappe.utils.now_datetime()):
                # return utils.respondUnauthorized(message=frappe._("OTP Expired."))
                raise lms.exceptions.UnauthorizedException("OTP Expired")

            if not user:
                # return utils.respondNotFound(message=frappe._("User not found."))
                raise lms.exceptions.NotFoundException(_("User not found"))

            # try:
            #     frappe.local.login_manager.check_if_enabled(user.name)
            # except frappe.SecurityException as e:
            #     return utils.respondUnauthorized(message=str(e))
            if not user.enabled:
                # return utils.respondUnauthorized(message="User disabled or missing")
                raise lms.exceptions.UnauthorizedException("User disabled or missing")

            customer = lms.__customer(user.name)
            try:
                user_kyc = lms.__user_kyc(user.name)
                user_kyc.pan_no = lms.user_details_hashing(user_kyc.pan_no)
                for i in user_kyc.bank_account:
                    i.account_number = lms.user_details_hashing(i.account_number)
            except UserKYCNotFoundException:
                user_kyc = {}

            res = {
                "token": utils.create_user_access_token(user.name),
                "customer": customer,
                "user_kyc": user_kyc,
            }

            if not is_dummy_account:
                token.used = 1
                token.save(ignore_permissions=True)

            app_version_platform = ""
            if data.get("app_version") and data.get("platform"):
                app_version_platform = (
                    data.get("app_version") + " | " + data.get("platform")
                )
            lms.add_firebase_token(
                data.get("firebase_token"), app_version_platform, user.name
            )
            lms.auth.login_activity(customer)
            frappe.db.commit()
            return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()
    except frappe.SecurityException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return utils.respondUnauthorized(message=str(e))
        # raise lms.exceptions.UnauthorizedException(str(e))


@frappe.whitelist(allow_guest=True)
def register(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "first_name": "required|alpha|max:25",
                "last_name": "max:25",
                "mobile": [
                    "required",
                    "decimal",
                    utils.validator.rules.LengthRule(10),
                    utils.validator.rules.ExistsRule(
                        doctype="User",
                        fields="username,mobile_no,phone",
                        message="Mobile already taken",
                    ),
                ],
                "email": [
                    "required",
                    utils.validator.rules.ExistsRule(
                        doctype="User", fields="email", message="Email already taken"
                    ),
                ],
                "firebase_token": "required",
                "platform": "",
                "app_version": "",
            },
        )
        reg = lms.regex_special_characters(search=data.get("last_name"))
        # for firebase token "-_:" these characters are excluded from regex string
        firebase_reg = lms.regex_special_characters(
            search=data.get("firebase_token"),
            regex=re.compile("[@!#$%^&*()<>?/\|}{~`]"),
        )
        # email validation
        # email_regex = r"^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,}$"
        email_regex = (
            r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
        )
        if re.search(email_regex, data.get("email")) is None or (
            len(data.get("email").split("@")) > 2
        ):
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Please enter valid email ID"),
            # )
            raise lms.exceptions.FailureException(_("Please enter valid email ID."))

        if reg or firebase_reg:
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        is_dummy_account = lms.validate_spark_dummy_account(data.get("mobile"))
        if is_dummy_account:
            is_valid_dummy_account = lms.validate_spark_dummy_account(
                data.get("mobile"), email=data.get("email"), check_valid=True
            )

            if not is_valid_dummy_account:
                # return utils.respondWithFailure(
                #     status=422,
                #     message=frappe._("Invalid Mobile or Email."),
                # )
                raise lms.exceptions.FailureException(_("Invalid Mobile or Email."))

        tester = frappe.get_all("Spark Tester", fields=["email_id"])
        emails = [e["email_id"] for e in tester if tester]

        user_data = {
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "mobile": data.get("mobile"),
            "email": data.get("email"),
            "tester": True if data.get("email") in emails else False,
        }
        # frappe.db.begin()
        user = lms.create_user(**user_data)
        customer = lms.create_customer(user)

        if not is_dummy_account:
            lms.create_user_token(
                entity=data.get("email"),
                token=lms.random_token(),
                token_type="Email Verification Token",
            )
        else:
            customer.is_email_verified = 1
            customer.save(ignore_permissions=True)

        app_version_platform = ""
        if data.get("app_version") and data.get("platform"):
            app_version_platform = (
                data.get("app_version") + " | " + data.get("platform")
            )
        lms.add_firebase_token(
            data.get("firebase_token"), app_version_platform, user.name
        )
        data = {
            "token": utils.create_user_access_token(user.name),
            "customer": customer,
        }
        frappe.db.commit()
        lms.auth.login_activity(customer)
        return utils.respondWithSuccess(
            message=frappe._("Registered Successfully."), data=data
        )
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def request_verification_email():
    try:
        # validation
        lms.validate_http_method("POST")

        lms.create_user_token(
            entity=frappe.session.user,
            token=lms.random_token(),
            token_type="Email Verification Token",
        )

        return lms.generateResponse(message=_("Verification email sent"))
    except (lms.ValidationError, lms.ServerError) as e:
        lms.log_api_error()
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        lms.log_api_error()
        return lms.generateResponse(is_success=False, error=e)


@frappe.whitelist()
def resend_verification_email(email):
    try:
        user_token = frappe.get_last_doc(
            "User Token",
            filters={"entity": email, "token_type": "Email Verification Token"},
        )
        if not user_token.used:
            doc = frappe.get_doc("User", email).as_dict()
            doc["url"] = frappe.utils.get_url(
                "/api/method/lms.auth.verify_user?token={}&user={}".format(
                    user_token.token, email
                )
            )
            frappe.enqueue_doc(
                "Notification",
                "User Email Verification",
                method="send",
                doc=doc,
            )
            frappe.msgprint(
                msg="Verification email resent Successfully",
                title="Email Verification",
                indicator="green",
            )
        else:
            lms.create_user_token(
                entity=email,
                token=lms.random_token(),
                token_type="Email Verification Token",
            )
            frappe.msgprint(
                msg="Verification email sent Successfully",
                title="Email Verification",
                indicator="green",
            )
    except Exception as e:
        lms.log_api_error()
        frappe.log_error(
            frappe.get_traceback() + "\nResend Email Info:\n" + json.dumps(email),
            e.args,
        )


@frappe.whitelist(allow_guest=True)
def verify_user(token, user):
    token_document = frappe.db.get_all(
        "User Token",
        filters={
            "entity": user,
            "token_type": "Email Verification Token",
            "token": token,
            # "used": 0,
        },
        fields=["*"],
    )

    url = frappe.utils.get_url("/everify")
    if token_document:
        if token_document[0].used == 0:
            url = frappe.utils.get_url("/everify?success")
            frappe.db.set_value("User Token", token_document[0].name, "used", 1)
            customer = lms.get_customer(user)
            customer.is_email_verified = 1
            customer.save(ignore_permissions=True)
            frappe.db.commit()

        elif token_document[0].used == 1:
            url = frappe.utils.get_url("/everify?already-verified")

    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = url

    # webbrowser.open(url, new=1)
    # if len(token_document) == 0:
    #     return frappe.respond_as_web_page(
    #         frappe._("Something went wrong"),
    #         frappe._("Your token is invalid."),
    #         indicator_color="red",
    #     )

    # if (
    #     len(token_document) > 0
    #     and token_document[0].expiry < frappe.utils.now_datetime()
    # ):
    #     return frappe.respond_as_web_page(
    #         frappe._("Something went wrong"),
    #         frappe._("Verification link has been Expired!"),
    #         indicator_color="red",
    #     )

    # frappe.db.set_value("User Token", token_document[0].name, "used", 1)
    # customer = lms.get_customer(user)
    # customer.is_email_verified = 1
    # customer.save(ignore_permissions=True)
    # frappe.db.commit()

    """changes as per latest email notification list-sent by vinayak - email verification final 2.0"""
    # doc = frappe.get_doc("User", user)

    # frappe.enqueue_doc("Notification", "User Welcome Email", method="send", doc=doc)

    # mess = frappe._(
    #     "Dear"
    #     + " "
    #     + customer.first_name
    #     + ",\nYour registration at Spark.Loans was successfull!\nWelcome aboard."
    # )
    # mess = frappe._("Welcome aboard. Your registration at Spark.Loans was successfull!")
    # frappe.enqueue(method=send_sms, receiver_list=[doc.phone], msg=mess)

    # frappe.respond_as_web_page(
    #     frappe._("Success"),
    #     frappe._("Your email has been successfully verified."),
    #     indicator_color="green",
    # )


@frappe.whitelist(allow_guest=True)
def request_forgot_pin_otp(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {"email": ["required"]},
        )
        # email validation
        # email_regex = r"^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,}$"
        email_regex = (
            r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
        )
        if re.search(email_regex, data.get("email")) is None or (
            len(data.get("email").split("@")) > 2
        ):
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Please enter valid email ID"),
            # )
            raise lms.exceptions.FailureException(_("Please enter valid email ID."))

        try:
            user = frappe.get_doc("User", data.get("email"))
        except frappe.DoesNotExistError:
            # raise utils.respondNotFound(
            #     message=frappe._("Please use registered email.")
            # )
            raise lms.exceptions.NotFoundException(_("Please use registered email."))

        if not user.enabled:
            # return utils.respondUnauthorized(message="User disabled or missing")
            raise lms.exceptions.UnauthorizedException(_("User disabled or missing"))

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, data.get("email"), check_valid=True
        )
        if not is_dummy_account:
            old_token_name = frappe.get_all(
                "User Token",
                filters={"entity": user.email, "token_type": "Forgot Pin OTP"},
                order_by="creation desc",
                fields=["*"],
            )
            if old_token_name:
                old_token = frappe.get_doc("User Token", old_token_name[0].name)
                lms.token_mark_as_used(old_token)

            # frappe.db.begin()
            lms.create_user_token(
                entity=user.email,
                token_type="Forgot Pin OTP",
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="Forgot Pin OTP sent")
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist(allow_guest=True)
def verify_forgot_pin_otp(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "email": ["required"],
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
                "new_pin": ["required", "decimal", utils.validator.rules.LengthRule(4)],
                "retype_pin": [
                    "required",
                    "decimal",
                    utils.validator.rules.LengthRule(4),
                ],
            },
        )
        # email validation
        # email_regex = r"^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,}$"
        email_regex = (
            r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
        )
        if re.search(email_regex, data.get("email")) is None or (
            len(data.get("email").split("@")) > 2
        ):
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Please enter valid email ID"),
            # )
            raise lms.exceptions.FailureException(_("Please enter valid email ID."))

        try:
            user = frappe.get_doc("User", data.get("email"))
        except frappe.DoesNotExistError:
            # raise utils.respondNotFound(
            #     message=frappe._("Please use registered email.")
            # )
            raise lms.exceptions.NotFoundException(_("Please use registered email."))

        if not user.enabled:
            # return utils.respondUnauthorized(message="User disabled or missing")
            raise lms.exceptions.UnauthorizedException(_("User disabled or missing"))

        try:
            is_dummy_account = lms.validate_spark_dummy_account(
                user.username, data.get("email"), check_valid=True
            )
            if not is_dummy_account:
                token = lms.verify_user_token(
                    entity=data.get("email"),
                    token=data.get("otp"),
                    token_type="Forgot Pin OTP",
                )
            else:
                token = lms.validate_spark_dummy_account_token(
                    user.username, data.get("otp"), token_type="Forgot Pin OTP"
                )
        except InvalidUserTokenException:
            # raise utils.respondForbidden(message=frappe._("Invalid Forgot Pin OTP."))
            raise lms.exceptions.ForbiddenException(_("Invalid Forgot Pin OTP"))

        # frappe.db.begin()

        if token and not is_dummy_account:
            if token.expiry <= frappe.utils.now_datetime():
                # return utils.respondUnauthorized(message=frappe._("OTP Expired."))
                raise lms.exceptions.UnauthorizedException(_("OTP Expired"))

        if data.get("otp") and data.get("new_pin") and data.get("retype_pin"):
            if data.get("retype_pin") == data.get("new_pin"):
                # update pin
                update_password(data.get("email"), data.get("retype_pin"))
                frappe.db.commit()

                return utils.respondWithSuccess(
                    message=frappe._("User PIN has been updated.")
                )

            else:
                # return utils.respondWithFailure(
                #     status=417, message=frappe._("Please retype correct pin.")
                # )
                raise lms.exceptions.RespondFailureException(
                    _("Please retype correct pin.")
                )

        elif not data.get("retype_pin") or not data.get("new_pin"):
            # return utils.respondWithFailure(
            #     status=417,
            #     message=frappe._("Please Enter value for new pin and retype pin."),
            # )
            raise lms.exceptions.RespondFailureException(
                _("SPlease Enter value for new pind and retype pin.")
            )

        if not is_dummy_account:
            lms.token_mark_as_used(token)

    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()


def login_activity(customer):
    activity_log = frappe.get_doc(
        {
            "doctype": "Activity Log",
            "owner": customer.user,
            "subject": customer.full_name + " logged in",
            "communication_date": frappe.utils.now_datetime(),
            "operation": "Login",
            "status": "Success",
            "user": customer.user,
            "full_name": customer.full_name,
        }
    )
    activity_log.insert(ignore_permissions=True)
    frappe.db.commit()


@frappe.whitelist(allow_guest=True)
def onboarding_screen():
    try:
        las_settings = frappe.get_single("LAS Settings")
        onboard_list = []
        for i in las_settings.onboarding_screen:
            onboard_screen = frappe.get_doc("Tutorial Screen", i.name)
            res = {
                "screen_no": onboard_screen.screen_no,
                "title": onboard_screen.title,
                "description": onboard_screen.description,
            }
            onboard_list.append(res)

        return utils.respondWithSuccess(message=onboard_list)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()
