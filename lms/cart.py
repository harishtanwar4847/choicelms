import json
import os
import re
from datetime import datetime, timedelta
from itertools import groupby

import frappe
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from num2words import num2words

import lms
from lms.exceptions import PledgeSetupFailureException
from lms.lms.doctype.approved_terms_and_conditions.approved_terms_and_conditions import (
    ApprovedTermsandConditions,
)


def validate_securities_for_cart(securities, lender, instrument_type="Shares"):
    msg = "securities"
    if instrument_type == "Mutual Fund":
        msg = "schemes"

    if not securities or (
        type(securities) is not dict and "list" not in securities.keys()
    ):
        raise utils.exceptions.ValidationException(
            {
                "securities": {
                    "required": frappe._("{msg} required.".format(msg=msg.title()))
                }
            }
        )

    securities = securities["list"]

    if len(securities) == 0:
        raise utils.exceptions.ValidationException(
            {
                "securities": {
                    "required": frappe._("{msg} required.".format(msg=msg.title()))
                }
            }
        )

    # check if securities is a list of dict
    securities_valid = True

    if type(securities) is not list:
        securities_valid = False
        message = frappe._("{msg} should be list of dictionaries".format(msg=msg))

    securities_list = [i["isin"] for i in securities]

    if securities_valid:
        if len(set(securities_list)) != len(securities_list):
            securities_valid = False
            message = frappe._("duplicate isin")

    if securities_valid:
        securities_list_from_db_ = frappe.db.sql(
            "select isin from `tabAllowed Security` where lender = '{}' and instrument_type = '{}' and isin in {}".format(
                lender,
                instrument_type,
                lms.convert_list_to_tuple_string(securities_list),
            )
        )
        securities_list_from_db = [i[0] for i in securities_list_from_db_]

        diff = list(set(securities_list) - set(securities_list_from_db))
        if diff:
            securities_valid = False
            message = frappe._("{} isin not found".format(",".join(diff)))

    if securities_valid:
        for i in securities:
            if type(i) is not dict:
                securities_valid = False
                message = frappe._(
                    "items in {msg} need to be dictionaries".format(msg=msg)
                )
                break

            keys = i.keys()
            if "isin" not in keys or "quantity" not in keys:
                securities_valid = False
                message = frappe._("isin or quantity not present")
                break

            if i.get("quantity") <= 0:
                securities_valid = False
                message = frappe._("quantity should be more than 0")
                break

    if not securities_valid:
        raise utils.exceptions.ValidationException(
            {"securities": {"required": message}}
        )

    return securities


@frappe.whitelist()
def upsert(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "securities": "",
                "cart_name": "",
                "loan_name": "",
                "loan_margin_shortfall_name": "",
                "lender": "",
                "pledgor_boid": "",
                "instrument_type": "",
                "scheme_type": "",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("cart_name")
            + data.get("loan_name")
            + data.get("loan_margin_shortfall_name")
            + data.get("lender")
            + data.get("pledgor_boid")
            + data.get("instrument_type")
            if data.get("instrument_type", None)
            else "" + data.get("scheme_type")
            if data.get("scheme_type", None)
            else ""
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        for security in data.get("securities")["list"]:
            quantity_split_list = str(security["quantity"]).split(".")
            if len(quantity_split_list) > 1 and len(quantity_split_list[-1]) > 3:
                return utils.respondWithFailure(
                    status=422,
                    message=frappe._(
                        "Unit of {} should be in 3 digit precision.".format(
                            security["isin"]
                        )
                    ),
                )

        if not data.get("instrument_type"):
            data["instrument_type"] = "Shares"

        if not data.get("pledgor_boid") and data.get("instrument_type") == "Shares":
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Pledgor boid required."),
            )

        if data.get("pledgor_boid") and data.get("instrument_type") == "Mutual Fund":
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Pledgor boid not required."),
            )

        if data.get("instrument_type") == "Mutual Fund" and not (
            data.get("scheme_type") == "Debt" or data.get("scheme_type") == "Equity"
        ):
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Please select Equity or Debt as Scheme type."),
            )

        if not data.get("lender", None):
            data["lender"] = "Choice Finserv"

        if data.get("instrument_type") == "Shares":
            data["scheme_type"] = ""

        securities = validate_securities_for_cart(
            securities=data.get("securities", {}),
            lender=data.get("lender"),
            instrument_type=data.get("instrument_type"),
        )

        # Min max sanctioned_limit
        lender = frappe.get_doc("Lender", data.get("lender"))

        min_sanctioned_limit = lender.minimum_sanctioned_limit
        max_sanctioned_limit = lender.maximum_sanctioned_limit

        customer = lms.__customer()
        if data.get("loan_name", None):
            try:
                loan = frappe.get_doc("Loan", data.get("loan_name"))
            except frappe.DoesNotExistError:
                return utils.respondNotFound(message=frappe._("Loan not found."))
            if loan.customer != customer.name:
                return utils.respondForbidden(
                    message=frappe._("Please use your own loan.")
                )

            # If pledge more/margin shortfall/increase Loan
            sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                loan.total_collateral_value * loan.allowable_ltv / 100
            )

            if data.get("loan_margin_shortfall_name", None):
                try:
                    loan_margin_shortfall = frappe.get_doc(
                        "Loan Margin Shortfall", data.get("loan_margin_shortfall_name")
                    )
                except frappe.DoesNotExistError:
                    return utils.respondNotFound(
                        message=frappe._("Loan Margin Shortfall not found.")
                    )
                if loan_margin_shortfall.status == "Sell Triggered":
                    return utils.respondWithFailure(
                        status=417,
                        message=frappe._("Sale is Triggered"),
                    )
                if loan.name != loan_margin_shortfall.loan:
                    return utils.respondForbidden(
                        message=frappe._(
                            "Loan Margin Shortfall should be for the provided loan."
                        )
                    )
                under_process_la = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": loan.name,
                        "status": [
                            "not IN",
                            ["Approved", "Rejected", "Pledge Failure"],
                        ],
                        "pledge_status": ["!=", "Failure"],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                if under_process_la:
                    return utils.respondWithFailure(
                        status=417,
                        message="Payment for Margin Shortfall of Loan {} is already in process.".format(
                            loan.name
                        ),
                    )
        # instrument_type = "Shares"
        # scheme_type = ""
        # if data.get("instrument_type") == "Mutual Fund":
        #     instrument_type = "Mutual Fund"
        #     if data.get("scheme_type") == "Equity":
        #         scheme_type = "Equity"
        #     elif data.get("scheme_type") == "Debt":
        #         scheme_type = "Debt"

        if not data.get("cart_name", None):
            cart = frappe.get_doc(
                {
                    "doctype": "Cart",
                    "customer": customer.name,
                    "customer_name": customer.full_name,
                    "lender": data.get("lender"),
                    "pledgor_boid": data.get("pledgor_boid"),
                    "instrument_type": data.get("instrument_type"),
                    "scheme_type": data.get("scheme_type"),
                }
            )
        else:
            cart = frappe.get_doc("Cart", data.get("cart_name"))
            cart.instrument_type = data.get("instrument_type")
            cart.scheme_type = data.get("scheme_type")
            cart.save(ignore_permissions=True)
            frappe.db.commit()
            cart.reload()

            if not cart:
                return utils.respondNotFound(message=frappe._("Cart not found."))
            if cart.customer != customer.name:
                return utils.respondForbidden(
                    message=frappe._("Please use your own cart.")
                )

            cart.items = []

        frappe.db.begin()
        for i in securities:
            cart.append(
                "items",
                {
                    "isin": i["isin"],
                    "pledged_quantity": i["quantity"],
                    "type": data.get("scheme_type")
                    if data.get("scheme_type")
                    else "Shares",
                },
            )
        cart.save(ignore_permissions=True)

        res = {"cart": cart}

        if data.get("loan_name", None):
            loan_margin_shortfall = loan.get_margin_shortfall()
            cart.loan = data.get("loan_name")
            if data.get("loan_margin_shortfall_name", None):
                cart.loan_margin_shortfall = data.get("loan_margin_shortfall_name")
            cart.save(ignore_permissions=True)

            if not loan_margin_shortfall.get("__islocal", 0):
                res["loan_margin_shortfall_obj"] = loan_margin_shortfall

            if sanctioned_limit < min_sanctioned_limit and not data.get(
                "loan_margin_shortfall_name"
            ):
                min_sanctioned_limit = min_sanctioned_limit - sanctioned_limit
            else:
                min_sanctioned_limit = 1000.0

        res["min_sanctioned_limit"] = (
            min_sanctioned_limit if not data.get("loan_margin_shortfall_name") else 0.0
        )
        res["max_sanctioned_limit"] = (
            max_sanctioned_limit if not data.get("loan_margin_shortfall_name") else 0.0
        )
        res["roi"] = lender.rate_of_interest

        frappe.db.commit()
        return utils.respondWithSuccess(data=res)
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        return e.respond()


@frappe.whitelist()
def process_old(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "cart_name": "required",
                "expiry": "",
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        user_kyc = lms.__user_kyc()

        token = lms.verify_user_token(
            entity=user_kyc.mobile_number,
            token=data.get("otp"),
            token_type="Pledge OTP",
        )

        if token.expiry <= frappe.utils.now_datetime():
            return utils.respondUnauthorized(message=frappe._("Pledge OTP Expired."))

        lms.token_mark_as_used(token)
        customer = lms.__customer()

        cart = frappe.get_doc("Cart", data.get("cart_name"))
        if not cart:
            return utils.respondNotFound(message=frappe._("Cart not found."))
        if cart.customer != customer.name:
            return utils.respondForbidden(message=frappe._("Please use your own cart."))

        pledge_request = cart.pledge_request()
        frappe.db.begin()
        # frappe.db.set_value(
        #     "Cart",
        #     cart.name,
        #     "prf_number",
        #     pledge_request.get("payload").get("PRFNumber"),
        # )

        try:
            res = requests.post(
                pledge_request.get("url"),
                headers=pledge_request.get("headers"),
                json=pledge_request.get("payload"),
            )
            data = res.json()

            # # Pledge LOG
            log = {
                "url": pledge_request.get("url"),
                "headers": pledge_request.get("headers"),
                "request": pledge_request.get("payload"),
                "response": data,
            }

            # pledge_log_file = frappe.utils.get_files_path("pledge_log.json")
            # pledge_log = None
            # if os.path.exists(pledge_log_file):
            #     with open(pledge_log_file, "r") as f:
            #         pledge_log = f.read()
            #     f.close()
            # pledge_log = json.loads(pledge_log or "[]")
            # pledge_log.append(log)
            # with open(pledge_log_file, "w") as f:
            #     f.write(json.dumps(pledge_log))
            # f.close()
            # Pledge LOG end

            lms.create_log(log, "pledge_log")

            if not res.ok or not data.get("Success"):
                cart.reload()
                # cart.status = "Failure"
                # cart.is_processed = 1
                cart.save(ignore_permissions=True)
                raise PledgeSetupFailureException(errors=res.text)

            cart.reload()
            cart.process(data)
            cart.save(ignore_permissions=True)
            loan_application = cart.create_loan_application()

            if not customer.pledge_securities:
                customer.pledge_securities = 1
                customer.save(ignore_permissions=True)
            frappe.db.commit()

            return utils.respondWithSuccess(data=loan_application)
        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        return e.respond()


@frappe.whitelist()
def process(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "cart_name": "required",
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        reg = lms.regex_special_characters(search=data.get("cart_name"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )
        user = lms.__user()
        user_kyc = lms.__user_kyc()
        customer = lms.__customer()

        cart = frappe.get_doc("Cart", data.get("cart_name"))
        if not cart:
            return utils.respondNotFound(message=frappe._("Cart not found."))
        if cart.customer != customer.name:
            return utils.respondForbidden(message=frappe._("Please use your own cart."))

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        token_type = "Pledge OTP"
        entity = user_kyc.mobile_number
        if cart.instrument_type == "Mutual Fund":
            token_type = "Lien OTP"
            entity = customer.phone

        if not is_dummy_account:
            token = lms.verify_user_token(
                entity=entity,
                token=data.get("otp"),
                token_type=token_type,
            )

            if token.expiry <= frappe.utils.now_datetime():
                return utils.respondUnauthorized(
                    message=frappe._("{} Expired.".format(token_type))
                )

            lms.token_mark_as_used(token)
        else:
            token = lms.validate_spark_dummy_account_token(
                user.username, data.get("otp"), token_type=token_type
            )

        frappe.db.begin()
        loan_application = {}
        cart.reload()
        if cart.instrument_type != "Mutual Fund":
            loan_application = cart.create_loan_application()
            frappe.db.commit()

        return utils.respondWithSuccess(
            data={
                "loan_application": loan_application,
                "mycam_url": ""
                if loan_application
                else frappe.utils.get_url(
                    "/mycams?cart_name={}".format(str(cart.name))
                ),
            }
        )
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        return e.respond()


"""
    # @frappe.whitelist()
    # def process_dummy(cart_name):
    #     cart = frappe.get_doc("Cart", cart_name)

    #     import random

    #     items = []
    #     ISINstatusDtls = []

    #     flag = 0
    #     for item in cart.items:
    #         # flag = bool(random.getrandbits(1))
    #         error_code = ["CIF3065-F", "PLD0152-E", "PLD0125-F"]
    #         ISINstatusDtls_item = {
    #             "ISIN": item.isin,
    #             "PSN": "" if flag else lms.random_token(7, is_numeric=True),
    #             "ErrorCode": random.choice(error_code) if flag else "",
    #         }
    #         ISINstatusDtls.append(ISINstatusDtls_item)

    #         item = frappe.get_doc(
    #             {
    #                 "doctype": "Loan Application Item",
    #                 "isin": item.isin,
    #                 "security_name": item.security_name,
    #                 "security_category": item.security_category,
    #                 "pledged_quantity": item.pledged_quantity,
    #                 "price": item.price,
    #                 "amount": item.amount,
    #                 "psn": ISINstatusDtls_item.get("PSN"),
    #                 "error_code": ISINstatusDtls_item.get("ErrorCode"),
    #             }
    #         )
    #         items.append(item)

    #     # dummy pledge request response
    #     data = {"Success": True, "PledgeSetupResponse": {"ISINstatusDtls": ISINstatusDtls}}

    #     cart.reload()
    #     cart.process(data)
    #     cart.save(ignore_permissions=True)

    #     # create loan application
    #     loan_application = frappe.get_doc(
    #         {
    #             "doctype": "Loan Application",
    #             "total_collateral_value": cart.total_collateral_value,
    #             "drawing_power": cart.eligible_loan,
    #             "lender": cart.lender,
    #             "status": "Esign Done",
    #             "pledgor_boid": "pledgor",
    #             "pledgee_boid": "pledgee",
    #             "prf_number": "prf",
    #             "expiry_date": "2021-01-31",
    #             "allowable_ltv": cart.allowable_ltv,
    #             "customer": cart.customer,
    #             "customer_name": cart.customer_name,
    #             "loan": cart.loan,
    #             "loan_margin_shortfall": cart.loan_margin_shortfall,
    #             "items": items,
    #         }
    #     )
    #     loan_application.insert(ignore_permissions=True)

    #     # save Collateral Ledger
    #     cart.save_collateral_ledger(loan_application.name)
    #     frappe.db.commit()

    #     customer = frappe.get_doc("Loan Customer", cart.customer)
    #     doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
    #     frappe.enqueue_doc(
    #         "Notification", "Loan Application Creation", method="send", doc=doc
    #     )

    #     mess = frappe._(
    #         "Dear "
    #         + doc.investor_name
    #         + ",\nYour pledge request and Loan Application was successfully accepted. \nPlease download your e-agreement - <Link>. \nApplication number: "
    #         + loan_application.name
    #         + ". \nYou will be notified once your OD limit is approved by our lending partner."
    #     )
    #     frappe.enqueue(method=send_sms, receiver_list=[doc.mobile_number], msg=mess)

    #     return loan_application.name
"""


@frappe.whitelist()
def request_pledge_otp(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs,
            {
                "instrument_type": "",
            },
        )
        reg = lms.regex_special_characters(
            data.get("instrument_type") if data.get("instrument_type") else ""
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        user = lms.__user()
        user_kyc = lms.__user_kyc()
        customer = lms.__customer()

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )

        token_type = "Pledge OTP"
        entity = user_kyc.mobile_number
        if data.get("instrument_type") == "Mutual Fund":
            token_type = "Lien OTP"
            entity = customer.phone
        if not is_dummy_account:
            frappe.db.begin()

            lms.create_user_token(
                entity=entity,
                token_type=token_type,
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="{} sent".format(token_type))
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        return e.respond()


@frappe.whitelist()
def get_tnc(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "cart_name": "",
                "loan_name": "",
                "topup_amount": [lambda x: type(x) == float],
            },
            # {"cart_name": ""},
        )

        reg = lms.regex_special_characters(
            search=data.get("cart_name")
            + data.get("loan_name")
            # search=data.get("cart_name")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        user_kyc = lms.__user_kyc()
        user = lms.__user()

        if data.get("cart_name") and data.get("loan_name"):
            return utils.respondForbidden(
                message=frappe._(
                    "Can not use both application at once, please use one."
                )
            )

        elif not data.get("cart_name") and not data.get("loan_name"):
            # if not data.get("cart_name"):
            return utils.respondForbidden(
                message=frappe._(
                    "Cart and Loan not found. Please use atleast one."
                    # "Cart name field empty"
                )
            )

        if data.get("cart_name"):
            if data.get("topup_amount"):
                return utils.respondWithFailure(
                    status=417,
                    message=frappe._("Do not enter topup amount for Cart."),
                )
            cart = frappe.get_doc("Cart", data.get("cart_name"))
            if not cart:
                return utils.respondNotFound(message=frappe._("Cart not found."))
            if cart.customer != customer.name:
                return utils.respondForbidden(
                    message=frappe._("Please use your own cart.")
                )
            lender = frappe.get_doc("Lender", cart.lender)
            if cart.loan:
                loan = frappe.get_doc("Loan", cart.loan)

        else:
            if not data.get("topup_amount"):
                return utils.respondWithFailure(
                    status=417,
                    message=frappe._("Please enter topup amount."),
                )
            loan = frappe.get_doc("Loan", data.get("loan_name"))
            if not loan:
                return utils.respondNotFound(message=frappe._("Loan not found."))
            if loan.customer != customer.name:
                return utils.respondForbidden(
                    message=frappe._("Please use your own Loan.")
                )
            loan = frappe.get_doc("Loan", data.get("loan_name"))
            lender = frappe.get_doc("Lender", loan.lender)

            # topup validation
            topup_amt = loan.max_topup_amount()

            existing_topup_application = frappe.get_all(
                "Top up Application",
                filters={
                    "loan": loan.name,
                    "customer": loan.customer,
                    "status": ["not IN", ["Approved", "Rejected"]],
                },
                fields=["count(name) as in_process"],
            )

            if existing_topup_application[0]["in_process"] > 0:
                return utils.respondForbidden(
                    message=_("Top up for {} is already in process.".format(loan.name))
                )
            elif not topup_amt:
                return utils.respondWithFailure(
                    status=417, message="Top up not available"
                )
            elif data.get("topup_amount") <= 0:
                return utils.respondWithFailure(
                    status=417, message="Top up amount can not be 0 or less than 0"
                )
            elif data.get("topup_amount") > topup_amt:
                return utils.respondWithFailure(
                    status=417,
                    message="Top up amount can not be more than Rs. {}".format(
                        topup_amt
                    ),
                )

            # msg = "Dear Customer,\nCongratulations! Your Top Up application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under 'Contact Us' on the app \n-Spark Loans"
            # receiver_list = list(
            #     set([str(customer.phone), str(customer.get_kyc().mobile_number)])
            # )
            # from frappe.core.doctype.sms_settings.sms_settings import send_sms

            # frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        tnc_ul = ["<ul>"]
        tnc_ul.append(
            "<li><strong> Name of borrower : {} </strong>".format(
                user_kyc.investor_name
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Address of borrower </strong> : {}".format(
                user_kyc.address or ""
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Nature of facility sanctioned :</strong> Loan Against Securities - Overdraft Facility;</li>"
        )
        tnc_ul.append(
            "<li><strong> Purpose </strong>: General purpose.<br />Note:-The facility shall not be used for anti-social or illegal purposes;</li>"
        )
        if data.get("cart_name"):
            if not cart.loan:
                tnc_ul.append(
                    "<li><strong> Sanctioned credit limit / Drawing power </strong>: <strong>Rs. {}/-</strong> (rounded to nearest 1000, lower side) (final limit will be based on the value of pledged securities at the time of acceptance of pledge. The drawing power is subject to change based on the pledged securities from time to time as also the value thereof determined by our Management as per our internal parameters from time to time);".format(
                        lms.validate_rupees(cart.eligible_loan)
                    )
                    + "</li>"
                )
            elif data.get("cart_name") and cart.loan and not cart.loan_margin_shortfall:
                increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                    (cart.total_collateral_value + loan.total_collateral_value)
                    * cart.allowable_ltv
                    / 100
                )
                tnc_ul.append(
                    "<li><strong> New sanctioned limit </strong>: <strong>Rs. {}/-</strong> (rounded to nearest 1000, lower side) (final limit will be based on the value of pledged securities at the time of acceptance of pledge. The drawing power is subject to change based on the pledged securities from time to time as also the value thereof determined by our Management as per our internal parameters from time to time);".format(
                        lms.validate_rupees(
                            increased_sanctioned_limit
                            if increased_sanctioned_limit
                            < lender.maximum_sanctioned_limit
                            else lender.maximum_sanctioned_limit
                        )
                    )
                    + "</li>"
                )
            # tnc_ul.append(
            #     "<li><strong> New Enhanced Credit Limit / Drawing Power </strong>: <strong>Rs. {}</strong> (Rounded to nearest 1000, lower side) (Final limit will be based on the Quantity and Value of pledged securities at the time of acceptance of pledge. The limit is subject to change based on the pledged shares from time to time as also the value thereof determined by our management as per our internal parameters from time to time);".format(
            #         lms.round_down_amount_to_nearest_thousand(
            #             (cart.total_collateral_value + loan.total_collateral_value)
            #             * cart.allowable_ltv
            #             / 100
            #         )
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Previous Credit Limit / Drawing Power </strong>: <strong>Rs. {}</strong>;".format(loan.drawing_power)+ "</li>")
        else:
            tnc_ul.append(
                "<li><strong> New sanctioned limit </strong>: <strong>Rs. {}/-</strong> (Rounded to nearest 1000, lower side) (final limit will be based on the value of pledged securities at the time of acceptance of pledge. The limit is subject to change based on the pledged shares from time to time as also the value thereof determined by our management as per our internal parameters from time to time);".format(
                    lms.validate_rupees(
                        data.get("topup_amount") + loan.sanctioned_limit
                    )
                )
                + "</li>"
            )
        tnc_ul.append("<li><strong> Interest type </strong>: Floating</li>")
        tnc_ul.append(
            "<li><strong> Rate of interest </strong>: <strong>{}%  per month</strong> after rebate, if paid within <strong>{} days</strong> of due date. Otherwise rebate of <strong>0.20%</strong> will not be applicable and higher interest rate will be applicable [Interest rate is subject to change based on the Management discretion from time to time];".format(
                lender.rate_of_interest, lender.rebait_threshold
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Details of security / collateral obtained </strong>: Shares and other securities as will be pledged from time to time to maintain the required security coverage;</li>"
        )
        tnc_ul.append(
            "<li><strong> Security coverage </strong>: Shares & Equity oriented Mutual Funds - <strong>Minimum 200%</strong><br />Other securities - As per rules applicable from time to time;</li>"
        )
        tnc_ul.append(
            "<li><strong> Facility tenure </strong>: 12 months (renewable at lender's discretion, as detailed in the T&C), <strong>Repayment is due</strong> within <strong>12 months</strong> of loan sanction.</li>"
        )
        tnc_ul.append(
            "<li><strong> Repayment through </strong>: Cash flows/Sale of securities/Other investments maturing;</li>"
        )
        tnc_ul.append(
            "<li><strong> Mode of communication</strong> of changes in interest rates and others : Website and Mobile App notification, SMS, email, letters, notices at branches, communication through statement of accounts of the borrower, or any other mode of communication;</li>"
        )
        tnc_ul.append("<li><strong> EMI payable </strong>: Not applicable;</li>")
        tnc_ul.append(
            "<li><strong> Penal interest rate / Penal charges </strong>: In case of occurrence of Event of Default (EOD), penal interest shall be charged <strong>upto 4.00% per month</strong> over and above applicable interest rate;</li>"
        )
        if lender.lender_processing_fees_type == "Percentage":
            tnc_ul.append(
                "<li><strong> Processing fees </strong>: <strong>{percent_charge}%</strong> of the sanctioned amount; subject to minimum amount of <strong>Rs. {min_amt}/-</strong> and maximum of <strong>Rs. {max_amt}/-</strong>".format(
                    percent_charge=lms.validate_percent(lender.lender_processing_fees),
                    min_amt=lms.validate_rupees(
                        lender.lender_processing_minimum_amount
                    ),
                    max_amt=lms.validate_rupees(
                        lender.lender_processing_maximum_amount
                    ),
                )
                + "</li>"
            )
        elif lender.lender_processing_fees_type == "Fix":
            tnc_ul.append(
                "<li><strong> Processing fees </strong>: <strong>Rs. {fix_charge}/-, {fix_charge_in_words} Only</strong>".format(
                    fix_charge=lms.validate_rupees(lender.lender_processing_fees),
                    fix_charge_in_words=lms.number_to_word(
                        lms.validate_rupees(lender.lender_processing_fees)
                    ).title(),
                )
                + "</li>"
            )
        if lender.renewal_charge_type == "Percentage":
            tnc_ul.append(
                "<li><strong> Account renewal charges </strong>: <strong>{percent_charge}%</strong> of the renewal amount (facility valid for a period of 12 months from the date of sanction; account renewal charges shall be debited at the end of 12 months) subject to minimum amount of <strong>Rs. {min_amt}/-</strong> and maximum of <strong>Rs. {max_amt}/-</strong>".format(
                    percent_charge=lms.validate_percent(lender.renewal_charges),
                    min_amt=lms.validate_rupees(lender.renewal_minimum_amount),
                    max_amt=lms.validate_rupees(lender.renewal_maximum_amount),
                )
                + "</li>"
            )
        elif lender.renewal_charge_type == "Fix":
            tnc_ul.append(
                "<li><strong> Account renewal charges </strong>: <strong>Rs. {fix_charge}/-, {fix_charge_in_words} Only</strong>".format(
                    fix_charge=lms.validate_rupees(lender.renewal_charges),
                    fix_charge_in_words=lms.number_to_word(
                        lms.validate_rupees(lender.renewal_charges)
                    ).title(),
                )
                + "</li>"
            )
        if lender.documentation_charge_type == "Percentage":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong> {percent_charge}%</strong> of the sanctioned amount; subject to minimum amount of <strong>Rs. {min_amt}/-</strong> and maximum of <strong>Rs. {max_amt}/-</strong>".format(
                    percent_charge=lms.validate_percent(lender.documentation_charges),
                    min_amt=lms.validate_rupees(
                        lender.lender_documentation_minimum_amount
                    ),
                    max_amt=lms.validate_rupees(
                        lender.lender_documentation_maximum_amount
                    ),
                )
                + "</li>"
            )
        elif lender.documentation_charge_type == "Fix":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong>Rs. {fix_charge}/-, {fix_charge_in_words} Only</strong>".format(
                    fix_charge=lms.validate_rupees(lender.documentation_charges),
                    fix_charge_in_words=lms.number_to_word(
                        lms.validate_rupees(lender.documentation_charges)
                    ).title(),
                )
                + "</li>"
            )
        # tnc_ul.append(
        #     "<li><strong> Stamp duty & other statutory charges : Rs. {}/-;</li></strong>".format(
        #         int(lender.lender_stamp_duty_minimum_amount)
        #     )
        # )
        tnc_ul.append(
            "<li><strong> Stamp duty & other statutory charges : At actuals;</li></strong>"
        )
        tnc_ul.append(
            "<li><strong> Pre-payment charges </strong>: <strong>NIL;</strong></li>"
        )
        tnc_ul.append(
            "<li><strong> Transaction charges per ISIN (per variation in the composition of the Demat securities pledged) </strong>: <strong>Upto Rs. {}/-</strong> per ISIN;".format(
                lms.validate_rupees(lender.transaction_charges_per_request)
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Collection Charges on Sale of security in the event of default or otherwise </strong>: <strong>{}%</strong> of the sale amount plus brokerage and other charges.<br />Note: The above includes incidental transaction charges, taxes, and other levies as per actuals;".format(
                lender.security_selling_share
            )
            + "</li>"
        )
        if lender.lien_initiate_charge_type == "Percentage":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong> {percent_charge}%</strong> of the sanctioned amount; subject to minimum amount of <strong>Rs. {min_amt}/-</strong> and maximum of <strong>Rs. {max_amt}/-</strong>".format(
                    percent_charge=lms.validate_percent(lender.lien_initiate_charges),
                    min_amt=lms.validate_rupees(
                        lender.lien_initiate_charge_minimum_amount
                    ),
                    max_amt=lms.validate_rupees(
                        lender.lien_initiate_charge_maximum_amount
                    ),
                )
                + "</li>"
            )
        elif lender.lien_initiate_charge_type == "Fix":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong>Rs. {fix_charge}/-, {fix_charge_in_words} Only</strong>".format(
                    fix_charge=lms.validate_rupees(lender.lien_initiate_charges),
                )
                + "</li>"
            )
        if lender.invoke_initiate_charge_type == "Percentage":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong> {percent_charge}%</strong> of the sanctioned amount; subject to minimum amount of <strong>Rs. {min_amt}/-</strong> and maximum of <strong>Rs. {max_amt}/-</strong>".format(
                    percent_charge=lms.validate_percent(lender.invoke_initiate_charges),
                    min_amt=lms.validate_rupees(
                        lender.invoke_initiate_charges_minimum_amount
                    ),
                    max_amt=lms.validate_rupees(
                        lender.invoke_initiate_charges_maximum_amount
                    ),
                )
                + "</li>"
            )
        elif lender.invoke_initiate_charge_type == "Fix":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong>Rs. {fix_charge}/-, {fix_charge_in_words} Only</strong>".format(
                    fix_charge=lms.validate_rupees(lender.invoke_initiate_charges),
                )
                + "</li>"
            )
        if lender.revoke_initiate_charge_type == "Percentage":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong> {percent_charge}%</strong> of the sanctioned amount; subject to minimum amount of <strong>Rs. {min_amt}/-</strong> and maximum of <strong>Rs. {max_amt}/-</strong>".format(
                    percent_charge=lms.validate_percent(lender.revoke_initiate_charges),
                    min_amt=lms.validate_rupees(
                        lender.revoke_initiate_charges_minimum_amount
                    ),
                    max_amt=lms.validate_rupees(
                        lender.revoke_initiate_charges_maximum_amount
                    ),
                )
                + "</li>"
            )
        elif lender.revoke_initiate_charge_type == "Fix":
            tnc_ul.append(
                "<li><strong> Documentation charges </strong>: <strong>Rs. {fix_charge}/-, {fix_charge_in_words} Only</strong>".format(
                    fix_charge=lms.validate_rupees(lender.revoke_initiate_charges),
                )
                + "</li>"
            )
        tnc_ul.append(
            "<li><strong> Credit Information Companies'(CICs) Charges </strong>: <strong>Upto Rs {}/-</strong> per instance (for individuals);".format(
                lms.validate_rupees(lender.cic_charges)
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Solvency Certificate </strong>: Not Applicable;</li>"
        )
        tnc_ul.append(
            "<li><strong> No Due Certificate / No Objection Certificate (NOC) </strong>: <strong>NIL;</strong></li>"
        )
        tnc_ul.append(
            "<li><strong> Legal & incidental charges </strong>: As per actuals;</li>"
        )
        tnc_ul.append(
            "<li><strong>Average Percentage Rate</strong> is maximum of <strong>20%</strong> inclusive of the annual interest rate, processing fee, documentation charges, stamp duty charges, renewal charges (if any).</li></ul>"
        )

        if data.get("cart_name"):
            cart.create_tnc_file()
            tnc_file_url = frappe.utils.get_url("files/tnc/{}.pdf".format(cart.name))

        else:
            loan.create_tnc_file(topup_amount=data.get("topup_amount"))
            tnc_file_url = frappe.utils.get_url("files/tnc/{}.pdf".format(loan.name))

        tnc_header = "Please refer to the <a href='{}'>Terms & Conditions</a> for LAS facility, for detailed terms.".format(
            tnc_file_url
        )
        # tnc_footer = "You shall be required to authenticate (in token of you having fully read and irrevocably and unconditionally accepted and authenticated) the above application for loan including the pledge request and the Terms and Conditions (which can be opened by clicking on the links) and entire contents thereof, by entering the OTP that will be sent to you next on your registered mobile number with CDSL."
        """Changes for Mutual Funds"""
        tnc_footer = "You shall be required to authenticate (in token of you having fully read and irrevocably and unconditionally accepted and authenticated) the above application for loan including the pledge request and the Terms and Conditions (which can be opened by clicking on the links) and entire contents thereof, by entering the OTP that will be sent to you next on your registered mobile number with CDSL (For Loan Against Shares) or spark.loans (For Loan Against Mutual Funds)"
        tnc_checkboxes = [
            i.tnc
            for i in frappe.get_all(
                "Terms and Conditions",
                filters={"is_active": 1},
                fields=["tnc"],
                order_by="creation asc",
            )
        ]

        res = {
            "tnc_file": tnc_file_url,
            "tnc_html": "".join(tnc_ul),
            "tnc_header": tnc_header,
            "tnc_footer": tnc_footer,
            "tnc_checkboxes": tnc_checkboxes,
        }

        for tnc in frappe.get_list("Terms and Conditions", filters={"is_active": 1}):
            # if data.get("loan_name"):
            #     top_up_approved_tnc = {
            #         "doctype": "Top up Application",
            #         "docname": data.get("loan_name"),
            #         "mobile": user.username,
            #         "tnc": tnc.name,
            #         "time": frappe.utils.now_datetime(),
            #     }
            #     ApprovedTermsandConditions.create_entry(**top_up_approved_tnc)
            #     frappe.db.commit()
            if data.get("cart_name"):
                cart_approved_tnc = {
                    "doctype": "Cart",
                    "docname": data.get("cart_name"),
                    "mobile": user.username,
                    "tnc": tnc.name,
                    "time": frappe.utils.now_datetime(),
                }
                ApprovedTermsandConditions.create_entry(**cart_approved_tnc)
                frappe.db.commit()

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        return e.respond()
