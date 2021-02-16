import json
from datetime import datetime, timedelta

import frappe
import utils
from frappe.auth import LoginManager, get_login_failed_count
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.utils.password import delete_login_failed_cache

import lms
from lms.exceptions.InvalidUserTokenException import InvalidUserTokenException
from lms.exceptions.UserKYCNotFoundException import UserKYCNotFoundException
from lms.exceptions.UserNotFoundException import UserNotFoundException


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
                "accept_terms": "",
            },
        )

        try:
            user = lms.__user(data.get("mobile"))
        except UserNotFoundException:
            user = None

        frappe.db.begin()
        if data.get("pin"):
            try:
                frappe.local.login_manager.authenticate(
                    user=user.name, pwd=data.get("pin")
                )
            except frappe.SecurityException as e:
                return utils.respondUnauthorized(message=str(e))
            except frappe.AuthenticationError as e:
                message = frappe._("Incorrect PIN.")
                invalid_login_attempts = get_login_failed_count(user.name)
                if invalid_login_attempts > 0:
                    message += " {} invalid {}.".format(
                        invalid_login_attempts,
                        "attempt" if invalid_login_attempts == 1 else "attempts",
                    )
                return utils.respondUnauthorized(message=message)
            customer = lms.__customer(user.name)
            try:
                user_kyc = lms.__user_kyc(user.name)
            except UserKYCNotFoundException:
                user_kyc = {}

            pending_loan_applications = frappe.get_all(
                "Loan Application",
                filters={
                    "customer": customer.name,
                    "status": "Pledge accepted by Lender",
                },
                fields=["*"],
            )

            pending_esigns = []
            if pending_loan_applications:
                for loan_application in pending_loan_applications:
                    loan_application_doc = frappe.get_doc(
                        "Loan Application", loan_application.name
                    )
                    pending_esigns.append(loan_application_doc)

            token = dict(
                token=utils.create_user_access_token(user.name),
                customer=customer,
                user_kyc=user_kyc,
                pending_esigns=pending_esigns,
            )
            lms.add_firebase_token(data.get("firebase_token"), user.name)
            return utils.respondWithSuccess(
                message=frappe._("Logged in Successfully"), data=token
            )
        else:
            if not data.get("accept_terms"):
                return utils.respondUnauthorized(
                    message=frappe._("Please accept Terms of Use and Privacy Policy.")
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

        lms.create_user_token(
            entity=data.get("mobile"), token=lms.random_token(length=4, is_numeric=True)
        )
        frappe.db.commit()
        return utils.respondWithSuccess(message=frappe._("OTP Sent"))
    except utils.APIException as e:
        frappe.db.rollback()
        return e.respond()


@frappe.whitelist()
def logout(firebase_token):
    get_user_token = frappe.db.get_value(
        "User Token", {"token_type": "Firebase Token", "token": firebase_token}
    )
    print(get_user_token)
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
        }
        return utils.respondWithSuccess(message=frappe._("success"), data=data)

    except utils.exceptions.APIException as e:
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
            },
        )

        try:
            token = lms.verify_user_token(
                entity=data.get("mobile"), token=data.get("otp"), token_type="OTP"
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
                frappe.local.login_manager.update_invalid_login(user.name)
                try:
                    frappe.local.login_manager.check_if_enabled(user.name)
                except frappe.SecurityException as e:
                    return utils.respondUnauthorized(message=str(e))

                invalid_login_attempts = get_login_failed_count(user.name)
                if invalid_login_attempts > 0:
                    message += " {} invalid {}.".format(
                        invalid_login_attempts,
                        "attempt" if invalid_login_attempts == 1 else "attempts",
                    )

            return utils.respondUnauthorized(message=message)

        if token:
            frappe.db.begin()
            if token.expiry <= datetime.now():
                return utils.respondUnauthorized(message=frappe._("OTP Expired."))

            if not user:
                return utils.respondNotFound(message=frappe._("User not found."))

            try:
                frappe.local.login_manager.check_if_enabled(user.name)
            except frappe.SecurityException as e:
                return utils.respondUnauthorized(message=str(e))
            customer = lms.__customer(user.name)
            try:
                user_kyc = lms.__user_kyc(user.name)
            except UserKYCNotFoundException:
                user_kyc = {}

            pending_loan_applications = frappe.get_all(
                "Loan Application",
                filters={
                    "customer": customer.name,
                    "status": "Pledge accepted by Lender",
                },
                fields=["*"],
            )

            pending_esigns = []
            if pending_loan_applications:
                for loan_application in pending_loan_applications:
                    loan_application_doc = frappe.get_doc(
                        "Loan Application", loan_application.name
                    )
                    pending_esigns.append(loan_application_doc)

            res = {
                "token": utils.create_user_access_token(user.name),
                "customer": customer,
                "user_kyc": user_kyc,
                "pending_esigns": pending_esigns,
            }
            token.used = 1
            token.save(ignore_permissions=True)
            lms.add_firebase_token(data.get("firebase_token"), user.name)
            frappe.db.commit()
            return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        return e.respond()


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
                    "mail",
                    utils.validator.rules.ExistsRule(
                        doctype="User", fields="email", message="Email already taken"
                    ),
                ],
                "firebase_token": "required",
            },
        )

        user_data = {
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "mobile": data.get("mobile"),
            "email": data.get("email"),
        }
        frappe.db.begin()
        user = lms.create_user(**user_data)
        customer = lms.create_customer(user)
        lms.create_user_token(
            entity=data.get("email"),
            token=lms.random_token(),
            token_type="Email Verification Token",
        )
        lms.add_firebase_token(data.get("firebase_token"), user.name)
        data = {
            "token": utils.create_user_access_token(user.name),
            "customer": customer,
        }
        frappe.db.commit()
        return utils.respondWithSuccess(
            message=frappe._("Registered Successfully."), data=data
        )
    except utils.APIException as e:
        frappe.db.rollback()
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
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)


@frappe.whitelist(allow_guest=True)
def verify_user(token, user):
    token_document = frappe.db.get_all(
        "User Token",
        filters={
            "entity": user,
            "token_type": "Email Verification Token",
            "token": token,
            "used": 0,
        },
        fields=["*"],
    )

    if len(token_document) == 0:
        return frappe.respond_as_web_page(
            frappe._("Something went wrong"),
            frappe._("Your token is invalid."),
            indicator_color="red",
        )

    if len(token_document) > 0 and token_document[0].expiry < datetime.now():
        return frappe.respond_as_web_page(
            frappe._("Something went wrong"),
            frappe._("Verification link has been Expired!"),
            indicator_color="red",
        )

    frappe.db.set_value("User Token", token_document[0].name, "used", 1)
    customer = lms.get_customer(user)
    customer.is_email_verified = 1
    customer.save(ignore_permissions=True)
    frappe.db.commit()

    doc = frappe.get_doc("User", user)

    frappe.enqueue_doc("Notification", "User Welcome Email", method="send", doc=doc)

    mess = frappe._(
        "Dear"
        + " "
        + customer.first_name
        + ",\nYour registration at Spark.Loans was successfull!\nWelcome aboard."
    )
    frappe.enqueue(method=send_sms, receiver_list=[doc.phone], msg=mess)

    frappe.respond_as_web_page(
        frappe._("Success"),
        frappe._("Your email has been successfully verified."),
        indicator_color="green",
    )
