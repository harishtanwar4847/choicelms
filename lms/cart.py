import re
from datetime import datetime, timedelta
from itertools import groupby

import frappe
import requests
import utils
from frappe.core.doctype.sms_settings.sms_settings import send_sms

import lms
from lms.exceptions import PledgeSetupFailureException
from lms.lms.doctype.approved_terms_and_conditions.approved_terms_and_conditions import (
    ApprovedTermsandConditions,
)


def validate_securities_for_cart(securities, lender):
    if not securities or (
        type(securities) is not dict and "list" not in securities.keys()
    ):
        raise utils.ValidationException(
            {"securities": {"required": frappe._("Securities required.")}}
        )

    securities = securities["list"]

    if len(securities) == 0:
        raise utils.ValidationException(
            {"securities": {"required": frappe._("Securities required.")}}
        )

    # check if securities is a list of dict
    securities_valid = True

    if type(securities) is not list:
        securities_valid = False
        message = frappe._("securities should be list of dictionaries")

    securities_list = [i["isin"] for i in securities]

    if securities_valid:
        if len(set(securities_list)) != len(securities_list):
            securities_valid = False
            message = frappe._("duplicate isin")

    if securities_valid:
        securities_list_from_db_ = frappe.db.sql(
            "select isin from `tabAllowed Security` where lender = '{}' and isin in {}".format(
                lender, lms.convert_list_to_tuple_string(securities_list)
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
                message = frappe._("items in securities need to be dictionaries")
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
        raise utils.ValidationException({"securities": {"required": message}})

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
                "pledgor_boid": "required",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("cart_name")
            + data.get("loan_name")
            + data.get("loan_margin_shortfall_name")
            + data.get("lender")
            + data.get("pledgor_boid")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        if not data.get("lender", None):
            data["lender"] = frappe.get_last_doc("Lender").name

        securities = validate_securities_for_cart(
            data.get("securities", {}), data.get("lender")
        )

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
            if data.get("loan_margin_shortfall_name", None):
                try:
                    loan_margin_shortfall = frappe.get_doc(
                        "Loan Margin Shortfall", data.get("loan_margin_shortfall_name")
                    )
                except frappe.DoesNotExistError:
                    return utils.respondNotFound(
                        message=frappe._("Loan Margin Shortfall not found.")
                    )
                if loan.name != loan_margin_shortfall.loan:
                    return utils.respondForbidden(
                        message=frappe._(
                            "Loan Margin Shortfall should be for the provided loan."
                        )
                    )

        if not data.get("cart_name", None):
            cart = frappe.get_doc(
                {
                    "doctype": "Cart",
                    "customer": customer.name,
                    "customer_name": customer.full_name,
                    "lender": data.get("lender"),
                    "pledgor_boid": data.get("pledgor_boid"),
                }
            )
        else:
            cart = frappe.get_doc("Cart", data.get("cart_name"))
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

        frappe.db.commit()
        return utils.respondWithSuccess(data=res)
    except utils.APIException as e:
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

            # Pledge LOG
            log = {
                "url": pledge_request.get("url"),
                "headers": pledge_request.get("headers"),
                "request": pledge_request.get("payload"),
                "response": data,
            }

            import json
            import os

            pledge_log_file = frappe.utils.get_files_path("pledge_log.json")
            pledge_log = None
            if os.path.exists(pledge_log_file):
                with open(pledge_log_file, "r") as f:
                    pledge_log = f.read()
                f.close()
            pledge_log = json.loads(pledge_log or "[]")
            pledge_log.append(log)
            with open(pledge_log_file, "w") as f:
                f.write(json.dumps(pledge_log))
            f.close()
            # Pledge LOG end

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
            raise utils.APIException(str(e))
    except utils.APIException as e:
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

        frappe.db.begin()
        cart.reload()
        cart.save(ignore_permissions=True)
        loan_application = cart.create_loan_application()
        frappe.db.commit()

        return utils.respondWithSuccess(data=loan_application)
    except utils.APIException as e:
        frappe.db.rollback()
        return e.respond()


@frappe.whitelist()
def process_dummy(cart_name):
    cart = frappe.get_doc("Cart", cart_name)

    import random

    items = []
    ISINstatusDtls = []

    flag = 0
    for item in cart.items:
        # flag = bool(random.getrandbits(1))
        error_code = ["CIF3065-F", "PLD0152-E", "PLD0125-F"]
        ISINstatusDtls_item = {
            "ISIN": item.isin,
            "PSN": "" if flag else lms.random_token(7, is_numeric=True),
            "ErrorCode": random.choice(error_code) if flag else "",
        }
        ISINstatusDtls.append(ISINstatusDtls_item)

        item = frappe.get_doc(
            {
                "doctype": "Loan Application Item",
                "isin": item.isin,
                "security_name": item.security_name,
                "security_category": item.security_category,
                "pledged_quantity": item.pledged_quantity,
                "price": item.price,
                "amount": item.amount,
                "psn": ISINstatusDtls_item.get("PSN"),
                "error_code": ISINstatusDtls_item.get("ErrorCode"),
            }
        )
        items.append(item)

    # dummy pledge request response
    data = {"Success": True, "PledgeSetupResponse": {"ISINstatusDtls": ISINstatusDtls}}

    cart.reload()
    cart.process(data)
    cart.save(ignore_permissions=True)

    # create loan application
    loan_application = frappe.get_doc(
        {
            "doctype": "Loan Application",
            "total_collateral_value": cart.total_collateral_value,
            "drawing_power": cart.eligible_loan,
            "lender": cart.lender,
            "status": "Esign Done",
            "pledgor_boid": "pledgor",
            "pledgee_boid": "pledgee",
            "prf_number": "prf",
            "expiry_date": "2021-01-31",
            "allowable_ltv": cart.allowable_ltv,
            "customer": cart.customer,
            "customer_name": cart.customer_name,
            "loan": cart.loan,
            "loan_margin_shortfall": cart.loan_margin_shortfall,
            "items": items,
        }
    )
    loan_application.insert(ignore_permissions=True)

    # save Collateral Ledger
    cart.save_collateral_ledger(loan_application.name)
    frappe.db.commit()

    customer = frappe.get_doc("Loan Customer", cart.customer)
    doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
    frappe.enqueue_doc(
        "Notification", "Loan Application Creation", method="send", doc=doc
    )

    mess = frappe._(
        "Dear "
        + doc.investor_name
        + ",\nYour pledge request and Loan Application was successfully accepted. \nPlease download your e-agreement - <Link>. \nApplication number: "
        + loan_application.name
        + ". \nYou will be notified once your OD limit is approved by our lending partner."
    )
    frappe.enqueue(method=send_sms, receiver_list=[doc.mobile_number], msg=mess)

    return loan_application.name


@frappe.whitelist()
def request_pledge_otp():
    try:
        utils.validator.validate_http_method("POST")

        user = lms.__user()
        user_kyc = lms.__user_kyc()

        frappe.db.begin()

        lms.create_user_token(
            entity=user_kyc.mobile_number,
            token_type="Pledge OTP",
            token=lms.random_token(length=4, is_numeric=True),
        )
        frappe.db.commit()
        return utils.respondWithSuccess(message="Pledge OTP sent")
    except utils.APIException as e:
        frappe.db.rollback()
        return e.respond()


@frappe.whitelist()
def get_tnc(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {"cart_name": "", "topup_application_name": ""},
        )

        reg = lms.regex_special_characters(
            search=data.get("cart_name") + data.get("topup_application_name")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        user_kyc = lms.__user_kyc()
        user = lms.__user()

        if data.get("cart_name") and data.get("topup_application_name"):
            return utils.respondForbidden(
                message=frappe._(
                    "Can not use both application at once, please use one."
                )
            )

        elif not data.get("cart_name") and not data.get("topup_application_name"):
            return utils.respondForbidden(
                message=frappe._(
                    "Cart and Top up Application not found. Please use atleast one."
                )
            )

        if data.get("cart_name"):
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
            topup_application = frappe.get_doc(
                "Top up Application", data.get("topup_application_name")
            )
            if not topup_application:
                return utils.respondNotFound(
                    message=frappe._("Topup Application not found.")
                )
            if topup_application.customer != customer.name:
                return utils.respondForbidden(
                    message=frappe._("Please use your own Topup Application.")
                )
            loan = frappe.get_doc("Loan", topup_application.loan)
            lender = frappe.get_doc("Lender", loan.lender)

        tnc_ul = ["<ul>"]
        tnc_ul.append(
            "<li><strong> Name Of Borrower : {} </strong>".format(
                user_kyc.investor_name
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Address Of Borrower </strong> : {}".format(
                user_kyc.address or ""
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Nature of facility sanctioned : Loan Against Securities - Overdraft facility;</strong></li>"
        )
        tnc_ul.append(
            "<li><strong> Purpose </strong>: General Purpose. The facility shall not be used for anti-social or illegal purposes;</li>"
        )
        if data.get("cart_name") and not cart.loan:
            tnc_ul.append(
                "<li><strong> Sanctioned Credit Limit / Drawing Power </strong>: <strong>Rs. {}</strong> (Rounded to nearest 1000, lower side) (Final limit will be based on the Quantity and Value of pledged securities at the time of acceptance of pledge. The limit is subject to change based on the pledged shares from time to time as also the value thereof determined by our management as per our internal parameters from time to time);".format(
                    cart.eligible_loan
                )
                + "</li>"
            )
        elif data.get("cart_name") and cart.loan:
            tnc_ul.append(
                "<li><strong> New Enhanced Credit Limit / Drawing Power </strong>: <strong>Rs. {}</strong> (Rounded to nearest 1000, lower side) (Final limit will be based on the Quantity and Value of pledged securities at the time of acceptance of pledge. The limit is subject to change based on the pledged shares from time to time as also the value thereof determined by our management as per our internal parameters from time to time);".format(
                    lms.round_down_amount_to_nearest_thousand(
                        (cart.total_collateral_value + loan.total_collateral_value)
                        * cart.allowable_ltv
                        / 100
                    )
                )
                + "</li>"
            )
            tnc_ul.append(
                "<li><strong> Previous Credit Limit / Drawing Power </strong>: <strong>Rs. {}</strong>;".format(loan.drawing_power)+ "</li>")
        else:
            tnc_ul.append(
                "<li><strong> Top up Amount </strong>: <strong>Rs. {}</strong> (Rounded to nearest 1000, lower side) (Final limit will be based on the Quantity and Value of pledged securities at the time of acceptance of pledge. The limit is subject to change based on the pledged shares from time to time as also the value thereof determined by our management as per our internal parameters from time to time);".format(
                    topup_application.top_up_amount + loan.drawing_power
                )
                + "</li>"
            )
        tnc_ul.append("<li><strong> Interest type </strong>: Floating</li>")
        tnc_ul.append(
            "<li><strong> Rate of Interest </strong>: <strong>{}%  per month</strong> after rebate, if paid within <strong>7 days</strong> of due date. Otherwise Rebate of <strong>0.20%</strong> will not be applicable and higher interest rate will be applicable [Interest rate is subject to change based on management discretion from time to time];".format(
                lender.rate_of_interest
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Details of security / Collateral obtained </strong>: Shares and other securities as will be pledged from time to time to maintain the required security coverage;</li>"
        )
        tnc_ul.append(
            "<li><strong> Security Coverage </strong>: Shares & Equity oriented Mutual Funds - <strong>Minimum 200%</strong>, Other Securities - As per rules applicable from time to time;</li>"
        )
        tnc_ul.append(
            "<li><strong> Facility Tenure </strong>: <strong>12 Months</strong> (Renewable at Lender’s discretion, as detailed in the T&C);</li>"
        )
        tnc_ul.append(
            "<li><strong> Repayment Through </strong>: Cash Flows /Sale of Securities/Other Investments Maturing;</li>"
        )
        tnc_ul.append(
            "<li><strong> Mode of communication</strong> of changes in interest rates and others : Website and Mobile App notification, SMS, Email, Letters, Notices at branches, communication through statement of accounts of the borrower, or any other mode of communication;</li>"
        )
        tnc_ul.append(
            "<li><strong> EMI Payable </strong>: <strong>Not Applicable;</strong></li>"
        )
        tnc_ul.append(
            "<li><strong> Penal Interest rate / Penal Charges </strong>: In case of occurrence of Event of Default (EOD), Penal Interest shall be charged <strong>upto 4.00% per month</strong> over and above applicable Interest Rate;</li>"
        )
        tnc_ul.append(
            "<li><strong> Processing Fee </strong>: <strong>{}%</strong> of the sanctioned amount, subject to minimum amount of <strong>Rs. 1500/-;</strong>".format(
                lender.lender_processing_fees
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Account Renewal charges </strong>: <strong>{}%</strong> of the renewal amount (Facility valid for a period of 12 months from the date of sanction; account renewal charges shall be debited at the end of 12 months), subject to minimum amount of <strong>Rs. 750/-;</strong>".format(
                lender.account_renewal_charges
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Documentation charges </strong>: <strong>Rs. {}/-;</strong>".format(
                lender.documentation_charges
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Stamp duty & other statutory charges </strong>: At actuals;</li>"
        )
        tnc_ul.append(
            "<li><strong> Pre-payment charges </strong>: <strong>NIL;</strong></li>"
        )
        tnc_ul.append(
            "<li><strong> Transaction Charges per Request (per variation in the composition of the Demat securities pledged) </strong>: <strong>Upto Rs. {}/-</strong> per request;".format(
                lender.transaction_charges_per_request
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Collection Charges on Sale of security in the event of default or otherwise </strong>: <strong>{}%</strong> of the sale amount plus all brokerage, incidental transaction charges, costs and expenses and other levies as per actuals;".format(
                lender.security_selling_share
            )
            + "</li>"
        )
        tnc_ul.append(
            "<li><strong> Credit Information Companies'(CICs) Charges </strong>: <strong>Upto Rs {}/-</strong> per instance (For individuals);".format(
                lender.cic_charges
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
            "<li><strong> Legal & incidental charges </strong>: As per actuals;</li></ul>"
        )

        if data.get("cart_name"):
            cart.create_tnc_file()
            tnc_file_url = frappe.utils.get_url("files/tnc/{}.pdf".format(cart.name))

        else:
            topup_application.create_tnc_file()
            tnc_file_url = frappe.utils.get_url(
                "files/tnc/{}.pdf".format(topup_application.name)
            )

        tnc_header = "Please refer to the <a href='{}'>Terms & Conditions</a> for LAS facility, for detailed terms.".format(
            tnc_file_url
        )
        tnc_footer = "You shall be required to authenticate (in token of you having fully read and irrevocably and unconditionally accepted and authenticated) the above application for loan including the pledge request and the Terms and Conditions (which can be opened by clicking on the links) and entire contents thereof, by entering the OTP that will be sent to you next on your registered mobile number with CDSL."
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
            if data.get("topup_application_name"):
                top_up_approved_tnc = {
                    "doctype": "Top up Application",
                    "docname": data.get("topup_application_name"),
                    "mobile": user.username,
                    "tnc": tnc.name,
                    "time": frappe.utils.now_datetime(),
                }
                ApprovedTermsandConditions.create_entry(**top_up_approved_tnc)
                frappe.db.commit()
            else:
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

    except utils.APIException as e:
        return e.respond()
