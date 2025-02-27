import base64
import hmac
import json
import os
import re
import time
from ctypes import util
from datetime import MINYEAR, date, datetime, time, timedelta
from random import choice, randint

import frappe
import pandas as pd
import requests
import utils
from frappe import _
from frappe.exceptions import DoesNotExistError
from frappe.utils.password import check_password, update_password
from utils.responder import respondWithFailure, respondWithSuccess

import lms
from lms import convert_sec_to_hh_mm_ss, holiday_list
from lms.exceptions import *
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.user_token.user_token import send_sms

special_char_not_allowed = "Special Characters not allowed."


@frappe.whitelist()
def set_pin(**kwargs):
    try:
        # validation
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "pin": ["required", "decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        update_password(frappe.session.user, data.get("pin"))
        frappe.db.commit()

        customer = lms.__customer()
        if customer.set_pin == 0:
            customer.set_pin = 1
            customer.save(ignore_permissions=True)
            frappe.db.commit

        return utils.respondWithSuccess(message=frappe._("User PIN has been set"))
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def schemes(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {"scheme_type": "", "lender": "", "level": ""},
        )

        reg = lms.regex_special_characters(
            search=data.get("scheme_type") + data.get("lender")
            if data.get("lender")
            else "" + data.get("level")
            if data.get("level")
            else ""
        )
        if reg:
            raise lms.exceptions.FailureException(_(special_char_not_allowed))

        if data.get("scheme_type") not in ["Equity", "Debt"]:
            raise lms.exceptions.FailureException(
                _("Scheme type should be either Equity or Debt.")
            )
        if not data.get("lender", None):
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Atleast one lender required"),
            )
        else:
            lender_list = data.get("lender").split(",")

        if not data.get("level"):
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Atleast one level required"),
            )

        if isinstance(data.get("level"), str):
            data["level"] = data.get("level").split(",")

        scheme = ""
        lender = ""
        sub_query = ""
        lender_clause = lms.convert_list_to_tuple_string(lender_list)
        lender = " and als.lender in {}".format(lender_clause)

        if data.get("scheme_type"):
            scheme = " and als.scheme_type = '{}'".format(data.get("scheme_type"))
        if data.get("level"):
            levels = lms.convert_list_to_tuple_string(data.get("level"))
            sub_query = " and als.security_category in (select security_category from `tabConcentration Rule` where parent in {} and idx in {})".format(
                lender_clause, levels
            )

        schemes_list = frappe.db.sql(
            """select als.isin, als.security_name as scheme_name, als.allowed, als.eligible_percentage as ltv, als.instrument_type, als.scheme_type, round(s.price,4) as price, group_concat(lender,'') as lenders, als.amc_code, am.amc_image
            from `tabAllowed Security` als
            LEFT JOIN `tabSecurity` s on s.isin = als.isin
            LEFT JOIN `tabAMC Master` am on am.amc_code = als.amc_code
            where als.instrument_type='Mutual Fund' and
            als.allowed = 1 and  s.price > 0{}{}{}
            group by als.isin
            order by als.creation desc;""".format(
                scheme, lender, sub_query
            ),
            as_dict=True,
            debug=True,
        )
        for scheme in schemes_list:
            if scheme.amc_image:
                scheme.amc_image = frappe.utils.get_url(scheme.amc_image)

        return utils.respondWithSuccess(
            message=frappe._("Success"), data={"schemes_list": schemes_list}
        )

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def isin_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {"isin": "required"},
        )

        reg = lms.regex_special_characters(search=data.get("isin"))
        if reg:
            raise lms.exceptions.FailureException(_(special_char_not_allowed))

        isin_details = frappe.db.sql(
            """select als.isin, als.eligible_percentage as ltv, als.category_name as category, l.name, l.minimum_sanctioned_limit, l.maximum_sanctioned_limit, l.rate_of_interest from `tabAllowed Security` als LEFT JOIN `tabLender` l on l.name = als.lender where als.isin='{}' Order by l.name""".format(
                data.get("isin")
            ),
            as_dict=True,
        )

        return utils.respondWithSuccess(
            message=frappe._("Success"), data={"isin_details": isin_details}
        )
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist(allow_guest=True)
def tds(tds_amount, year):

    files = frappe.request.files
    is_private = frappe.form_dict.is_private
    doctype = frappe.form_dict.doctype
    docname = frappe.form_dict.docname
    fieldname = frappe.form_dict.fieldname
    file_url = frappe.form_dict.file_url
    folder = frappe.form_dict.folder or "Home"
    method = frappe.form_dict.method
    content = None
    filename = None

    if "tds_file_upload" in files:
        file = files["tds_file_upload"]
        content = file.stream.read()
        filename = file.filename

    frappe.local.uploaded_file = content
    frappe.local.uploaded_filename = filename

    from frappe.utils import cint

    f = frappe.get_doc(
        {
            "doctype": "File",
            "attached_to_doctype": doctype,
            "attached_to_name": docname,
            "attached_to_field": fieldname,
            "folder": folder,
            "file_name": filename,
            "file_url": file_url,
            "is_private": cint(is_private),
            "content": content,
        }
    )
    f.save(ignore_permissions=True)
    tds = frappe.get_doc(
        dict(
            doctype="TDS", tds_amount=tds_amount, tds_file_upload=f.file_url, year=year
        )
    )
    tds.insert(ignore_permissions=True)

    return lms.generateResponse(
        message=frappe._("TDS Create Successfully."), data={"file": tds}
    )


"""Changes as per Concentration rule BRE"""


@frappe.whitelist()
def approved_securities(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {
                "lender": "required",
                "start": "decimal|min:0",
                "per_page": "decimal|min:0",
                "search": "",
                "category": "",
                "is_download": "decimal|between:0,1",
                "loan_type": "",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("lender") + data.get("category")
        )
        search_reg = lms.regex_special_characters(
            search=data.get("search"), regex=re.compile("[@!#$%_^&*<>?/\|}{~`]")
        )
        if reg or search_reg:
            raise lms.exceptions.FailureException(_(special_char_not_allowed))

        if isinstance(data.get("is_download"), str):
            data["is_download"] = int(data.get("is_download"))

        if data.get("loan_type") not in [
            "Equity",
            "Mutual Fund - Equity",
            "Mutual Fund - Debt",
        ]:
            raise lms.exceptions.FailureException(
                _(
                    "Loan type should be in Equity, Mutual Fund - Equity, Mutual Fund - Debt."
                )
            )

        if data.get("loan_type") == "Mutual Fund - Equity":
            data["loan_type"] = "Equity"
        elif data.get("loan_type") == "Mutual Fund - Debt":
            data["loan_type"] = "Debt"
        else:
            data["loan_type"] = "Shares"

        security_category_list_ = frappe.db.get_all(
            "Security Category",
            filters={"lender": data.get("lender")},
            fields=["distinct(category_name)"],
            order_by="category_name asc",
        )
        security_category_list = [i.category_name for i in security_category_list_]

        data["instrument_type"] = (
            "Shares" if data.get("loan_type") == "Shares" else "Mutual Fund"
        )

        filters = ""
        if data.get("loan_type", None) != "Shares":
            filters = "and scheme_type = '{}'".format(
                data.get("loan_type")
                if data.get("loan_type") in ["Equity", "Debt"]
                else ""
            )

        if data.get("search", None):
            search_key = "like " + str("'%" + data.get("search") + "%'")
            filters += "and security_name {}".format(search_key)

        if data.get("category", None):
            filters += " and security_category like '{}_%'".format(data.get("category"))

        approved_security_list = []
        approved_security_pdf_file_url = ""
        allowed = ""
        if data.get("instrument_type") == "Mutual Fund":
            allowed = "and alsc.allowed = 1"

        if data.get("is_download"):
            approved_security_list = frappe.db.sql(
                """
            select alsc.isin, alsc.security_name, alsc.allowed, alsc.eligible_percentage, alsc.category_name as security_category from `tabAllowed Security` alsc where lender = "{lender}" {allowed} and instrument_type = "{instrument_type}" {filters} order by security_name asc;""".format(
                    instrument_type=data.get("instrument_type"),
                    lender=data.get("lender"),
                    filters=filters,
                    allowed=allowed,
                ),
                as_dict=1,
            )

            approved_security_list.sort(
                key=lambda item: (item["security_name"]).title(),
            )

            if not approved_security_list:
                raise lms.exceptions.NotFoundException(_("No Record found"))

            lt_list = []

            for list in approved_security_list:
                lt_list.append(list.values())
            df = pd.DataFrame(lt_list)
            df.columns = approved_security_list[0].keys()
            df.drop("eligible_percentage", inplace=True, axis=1)
            df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()
            df.index += 1
            approved_security_pdf_file = "{}-approved-securities.pdf".format(
                data.get("lender")
            ).replace(" ", "-")

            date_ = frappe.utils.now_datetime()
            # formatting of date as 1 => 1st, 11 => 11th, 21 => 21st
            formatted_date = lms.date_str_format(date=date_.day)

            curr_date = formatted_date + date_.strftime(" %B, %Y")

            approved_security_pdf_file_path = frappe.utils.get_files_path(
                approved_security_pdf_file
            )

            lender = frappe.get_doc("Lender", data["lender"])
            las_settings = frappe.get_single("LAS Settings")
            logo_file_path_1 = lender.get_lender_logo_file()
            logo_file_path_2 = lender.get_lender_address_file()
            approved_securities_template = lender.get_approved_securities_template()
            doc = {
                "column_name": df.columns,
                "rows": df.iterrows(),
                "date": curr_date,
                "logo_file_path_1": logo_file_path_1.file_url
                if logo_file_path_1
                else "",
                "logo_file_path_2": logo_file_path_2.file_url
                if logo_file_path_2
                else "",
                "instrument_type": data.get("instrument_type"),
                "scheme_type": data.get("loan_type"),
                "is_html": lender.is_html,
                "lender_header": lender.lender_header,
                "lender_footer": lender.lender_footer,
            }
            agreement = frappe.render_template(
                approved_securities_template.get_content(), {"doc": doc}
            )

            pdf_file = open(approved_security_pdf_file_path, "wb")

            pdf = lms.get_pdf(
                agreement,
                options={
                    "margin-right": "1mm",
                    "margin-left": "1mm",
                    "page-size": "A4",
                },
            )
            pdf_file.write(pdf)
            pdf_file.close()

            approved_security_pdf_file_url = frappe.utils.get_url(
                "files/{}-approved-securities.pdf".format(data.get("lender")).replace(
                    " ", "-"
                )
            )
        else:
            if not data.get("per_page", None):
                data["per_page"] = 20
            if not data.get("start", None):
                data["start"] = 0

            approved_security_list = frappe.db.sql(
                """
            select alsc.isin, alsc.security_name, alsc.allowed, alsc.eligible_percentage, alsc.category_name as security_category from `tabAllowed Security` alsc where lender = "{lender}" {allowed} and instrument_type = "{instrument_type}" {filters} order by security_name asc limit {offset},{limit};""".format(
                    instrument_type=data.get("instrument_type"),
                    lender=data.get("lender"),
                    filters=filters,
                    allowed=allowed,
                    limit=data.get("per_page"),
                    offset=data.get("start"),
                ),
                as_dict=1,
            )

        res = {
            "security_category_list": security_category_list,
            "approved_securities_list": approved_security_list,
            "pdf_file_url": approved_security_pdf_file_url,
        }

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def all_loans_list(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        all_loans = frappe.get_all(
            "Loan", filters={"customer": customer.name}, order_by="creation desc"
        )

        return utils.respondWithSuccess(data=all_loans)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def my_pledge_securities(**kwargs):
    try:
        utils.validator.validate_http_method("GET")
        data = utils.validator.validate(
            kwargs,
            {"loan_name": ""},
        )
        customer = lms.__customer()
        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            raise lms.exceptions.FailureException(_(special_char_not_allowed))

        try:
            if data.get("loan_name"):
                loan = frappe.get_doc("Loan", data.get("loan_name"))
            elif not data.get("loan_name", None):
                latest_loan = frappe.get_all(
                    "Loan",
                    filters={"customer": customer.name},
                    order_by="creation desc",
                    page_length=1,
                )
                loan = frappe.get_doc("Loan", latest_loan[0].name)
        except frappe.DoesNotExistError:
            raise lms.exceptions.NotFoundException(_("Loan not found"))

        if loan.customer != customer.name:
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan"))

        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        all_pledged_securities = []
        for i in loan.get("items"):
            all_pledged_securities.append(
                {
                    "isin": i.get("isin"),
                    "security_name": i.get("security_name"),
                    "pledged_quantity": i.get("pledged_quantity"),
                    "security_category": i.get("security_category"),
                    "price": i.get("price"),
                    "amount": i.get("amount"),
                    "folio": i.get("folio"),
                    "eligible_percentage": i.get("eligible_percentage"),
                }
            )
        all_pledged_securities.sort(key=lambda item: item["security_name"])

        res = {
            "loan_name": loan.name,
            "instrument_type": loan.instrument_type,
            "scheme_type": loan.scheme_type if loan.scheme_type else "",
            "total_value": loan.total_collateral_value,
            "drawing_power": loan.drawing_power,
            "balance": loan.balance,
            "number_of_scrips": len(loan.items),
            "all_pledged_securities": all_pledged_securities,
        }

        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None

        # Sell Collateral
        sell_collateral_application_exist = frappe.get_all(
            "Sell Collateral Application",
            filters={"loan": loan.name, "status": "Pending"},
            order_by="creation desc",
            page_length=1,
        )
        res["sell_collateral"] = 1
        if len(sell_collateral_application_exist):
            res["sell_collateral"] = None

        res["is_sell_triggered"] = 0
        if loan_margin_shortfall:
            if loan_margin_shortfall.status == "Sell Triggered":
                res["is_sell_triggered"] = 1

        # Increase Loan
        existing_loan_application = frappe.get_all(
            "Loan Application",
            filters={
                "loan": loan.name,
                "customer": loan.customer,
                "status": ["not IN", ["Approved", "Rejected", "Pledge Failure"]],
            },
            fields=["count(name) as in_process", "name"],
        )

        res["increase_loan"] = None
        res["increase_loan_name"] = ""
        if existing_loan_application[0]["in_process"] == 0:
            res["increase_loan"] = 1
        else:
            res["increase_loan_name"] = existing_loan_application[0].name

        # for topup application
        existing_topup_application = frappe.get_all(
            "Top up Application",
            filters={
                "loan": loan.name,
                "customer": loan.customer,
                "status": ["not IN", ["Approved", "Rejected"]],
            },
            fields=["count(name) as in_process", "name"],
        )

        res["topup_application"] = None
        res["topup_application_name"] = ""
        if existing_topup_application[0]["in_process"] == 0:
            res["topup_application"] = 1
        else:
            res["topup_application_name"] = existing_topup_application[0].name

        # check if any pending unpledge application exist
        unpledge_application_exist = frappe.get_all(
            "Unpledge Application",
            filters={"loan": loan.name, "status": "Pending"},
            order_by="creation desc",
            page_length=1,
        )
        if len(unpledge_application_exist):
            res["unpledge"] = None
        else:
            # get amount_available_for_unpledge,min collateral value
            msg_type = ["unpledge", "pledged securities"]
            if loan.instrument_type == "Mutual Fund":
                msg_type = ["revoke", "liened schemes"]

            res["unpledge"] = dict(
                unpledge_msg_while_margin_shortfall="""OOPS! Dear {}, It seems you have a margin shortfall. You cannot {} any of the {} until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                    loan.get_customer().first_name, msg_type[0], msg_type[1]
                )
                if loan_margin_shortfall
                else None,
            )

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def dashboard(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        user = lms.__user()
        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))
        try:
            if customer.choice_kyc:
                user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            else:
                user_kyc = lms.__user_kyc()
            user_kyc = lms.user_kyc_hashing(user_kyc)
        except UserKYCNotFoundException:
            user_kyc = None

        mgloan = []
        deadline_for_all_mg_shortfall = {}
        total_int_amt_all_loans = 0
        due_date_for_all_interest = []
        interest_loan_list = []
        margin_shortfall_and_interest_loans = (
            lms.user.margin_shortfall_and_interest_loans(customer)
        )

        for dictionary in margin_shortfall_and_interest_loans[0]:
            loan = frappe.get_doc("Loan", dictionary["name"])
            mg_shortfall_doc = loan.get_margin_shortfall()

            if mg_shortfall_doc:
                is_today_holiday = 0
                hrs_difference = mg_shortfall_doc.deadline - frappe.utils.now_datetime()

                if mg_shortfall_doc.creation.date() != mg_shortfall_doc.deadline.date():
                    date_array = set(
                        mg_shortfall_doc.creation.date() + timedelta(days=x)
                        for x in range(
                            0,
                            (
                                mg_shortfall_doc.deadline.date()
                                - mg_shortfall_doc.creation.date()
                            ).days
                            + 1,
                        )
                    )
                    holidays = date_array.intersection(
                        set(holiday_list(is_bank_holiday=1))
                    )

                    previous_holidays = 0
                    for days in list(holidays):
                        if (
                            days >= mg_shortfall_doc.creation.date()
                            and days < frappe.utils.now_datetime().date()
                        ):
                            previous_holidays += 1

                    hrs_difference = (
                        mg_shortfall_doc.deadline
                        - frappe.utils.now_datetime()
                        - timedelta(days=(len(holidays) if holidays else 0))
                        + timedelta(
                            days=previous_holidays
                        )  # if_prev_days_in_holidays then add those days in timer
                    )

                    if frappe.utils.now_datetime().date() in holidays:
                        start_time = frappe.utils.now_datetime().replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        is_today_holiday = 1
                        hrs_difference += frappe.utils.now_datetime() - start_time

                mgloan.append(
                    {
                        "name": dictionary["name"],
                        "status": dictionary["status"],
                        "deadline": convert_sec_to_hh_mm_ss(
                            abs(hrs_difference).total_seconds()
                        )
                        if mg_shortfall_doc.deadline > frappe.utils.now_datetime()
                        else "00:00:00",
                        "is_today_holiday": is_today_holiday,
                    }
                )

        ## taking min of deadline for the earliest deadline in list ##
        mgloan.sort(key=lambda item: item["deadline"])

        ## Margin Shortfall card ##
        if mgloan:
            deadline_for_all_mg_shortfall = {
                "earliest_deadline": mgloan[0].get("deadline"),
                "loan_with_margin_shortfall_list": mgloan,
            }
        # Interest ##
        for dictionary in margin_shortfall_and_interest_loans[1]:
            if dictionary["interest_amount"]:
                loan = frappe.get_doc("Loan", dictionary.get("name"))
                current_date = frappe.utils.now_datetime()
                due_date = ""
                due_date_txt = "Pay By"
                info_msg = ""
                dpd = loan.day_past_due

                rebate_threshold = int(loan.get_rebate_threshold())
                default_threshold = int(loan.get_default_threshold())
                if rebate_threshold:
                    due_date = (
                        (current_date.replace(day=1) - timedelta(days=1))
                        + timedelta(days=rebate_threshold)
                    ).replace(hour=23, minute=59, second=59, microsecond=999999)
                    info_msg = """Interest becomes due and payable on the last date of every month. Please pay within {0} days to enjoy rebate which has already been applied while calculating the Interest Due.  After {0} days, the interest is recalculated without appliying applicable rebate and the difference appears as "Additional Interest" in your loan account. If interest remains unpaid after {1} days from the end of the month, "Penal Interest Charges" are debited to the account. Please check your terms and conditions of sanction for details.""".format(
                        rebate_threshold, default_threshold
                    )

                    if current_date > due_date:
                        due_date_txt = "Immediate"

                total_int_amt_all_loans += round(dictionary["interest_amount"], 2)
                interest_loan_list.append(
                    {
                        "loan_name": dictionary["name"],
                        "interest_amount": round(dictionary["interest_amount"], 2),
                    }
                )

                interest = {
                    "due_date": due_date,
                    "due_date_txt": due_date_txt,
                    "info_msg": info_msg,
                }
            else:
                interest = None

            dictionary["interest"] = interest

            ## Due date and text for interest ##
            due_date_for_all_interest.append(
                {
                    "due_date": (dictionary["interest"]["due_date"]).strftime(
                        "%d.%m.%Y"
                    ),
                    "due_date_txt": dictionary["interest"]["due_date_txt"],
                    "dpd": dpd,
                }
            )

        ## taking min of due date for the earliest due date in list ##
        due_date_for_all_interest.sort(key=lambda item: item["due_date"])

        ## Interest card ##
        total_interest_all_loans = {}
        if due_date_for_all_interest:
            total_interest_all_loans = {
                "total_interest_amount": lms.amount_formatter(total_int_amt_all_loans),
                "loans_interest_due_date": due_date_for_all_interest[0],
                "interest_loan_list": interest_loan_list,
            }

        # pending esign object for loan application and topup application
        pending_loan_applications = frappe.get_all(
            "Loan Application",
            filters={"customer": customer.name, "status": "Pledge accepted by Lender"},
            fields=["*"],
        )

        la_pending_esigns = []
        sanction_letter = []
        if pending_loan_applications:
            for loan_application in pending_loan_applications:
                loan_application_doc = frappe.get_doc(
                    "Loan Application", loan_application.name
                )
                if loan_application_doc.sl_entries:
                    sanction_letter = frappe.db.sql(
                        """select sanction_letter from `tabSanction Letter Entries` where parent = '{parent}' and loan_application_no = '{name}'""".format(
                            parent=loan_application_doc.sl_entries,
                            name=loan_application_doc.name,
                        ),
                        as_dict=True,
                    )
                mess = (
                    "Congratulations! Your application is being considered favourably by our lending partner and finally accepted at Rs. {current_total_collateral_value} against the request value of Rs. {requested_total_collateral_value}. Accordingly, the increase in the sanctioned limit is Rs. {drawing_power}. Please e-sign the loan agreement to avail the increased sanctioned limit now.".format(
                        current_total_collateral_value=frappe.utils.fmt_money(
                            loan_application_doc.total_collateral_value
                        ),
                        requested_total_collateral_value=frappe.utils.fmt_money(
                            loan_application_doc.pledged_total_collateral_value
                        ),
                        drawing_power=frappe.utils.fmt_money(
                            loan_application_doc.drawing_power
                        ),
                    )
                    if loan_application_doc.loan
                    and not loan_application_doc.loan_margin_shortfall
                    and loan_application_doc.application_type != "Pledge More"
                    else "Congratulations! Your application is being considered favourably by our lending partner and finally accepted at Rs. {current_total_collateral_value} against the request value of Rs. {requested_total_collateral_value}. Accordingly the final Sanctioned Limit is Rs. {drawing_power}. Please e-sign the loan agreement to avail the loan now.".format(
                        current_total_collateral_value=frappe.utils.fmt_money(
                            loan_application_doc.total_collateral_value
                        ),
                        requested_total_collateral_value=frappe.utils.fmt_money(
                            loan_application_doc.pledged_total_collateral_value
                        ),
                        drawing_power=frappe.utils.fmt_money(
                            loan_application_doc.drawing_power
                        ),
                    )
                )
                if (
                    loan_application_doc.loan
                    and not loan_application_doc.loan_margin_shortfall
                    and loan_application_doc.application_type != "Pledge More"
                ):
                    loan = frappe.get_doc("Loan", loan_application_doc.loan)
                    increase_loan_mess = dict(
                        existing_limit=loan.sanctioned_limit,
                        existing_collateral_value=loan.total_collateral_value,
                        new_dp=loan.drawing_power + loan_application_doc.drawing_power,
                        new_limit=lms.round_down_amount_to_nearest_thousand(
                            loan.drawing_power + loan_application_doc.drawing_power
                        ),
                        new_collateral_value=loan_application_doc.total_collateral_value
                        + loan.total_collateral_value,
                    )

                if (
                    not loan_application_doc.loan_margin_shortfall
                    and loan_application_doc.application_type != "Pledge More"
                ):
                    la_pending_esigns.append(
                        {
                            "loan_application": loan_application_doc,
                            "message": mess,
                            "increase_loan_message": increase_loan_mess
                            if loan_application_doc.loan
                            and not loan_application_doc.loan_margin_shortfall
                            else None,
                            "sanction_letter": sanction_letter[0]
                            if sanction_letter
                            else None,
                        }
                    )

        pending_topup_applications = frappe.get_all(
            "Top up Application",
            filters={"customer": customer.name, "status": "Pending"},
            fields=["*"],
        )

        topup_pending_esigns = []
        sanction_letter = []
        if pending_topup_applications:
            for topup_application in pending_topup_applications:
                topup_application_doc = frappe.get_doc(
                    "Top up Application", topup_application.name
                ).as_dict()

                if topup_application_doc.sl_entries:
                    sanction_letter = frappe.db.sql(
                        """select sanction_letter from `tabSanction Letter Entries` where parent = '{parent}' and topup_application_no = '{name}'""".format(
                            parent=topup_application_doc.sl_entries,
                            name=topup_application_doc.name,
                        ),
                        as_dict=True,
                    )
                topup_amount = topup_application_doc.top_up_amount
                topup_application_doc.top_up_amount = lms.amount_formatter(
                    topup_application_doc.top_up_amount
                )
                topup_pending_esigns.append(
                    {
                        "topup_application_doc": topup_application_doc,
                        "mess": "Congratulations! Your application is being considered favourably by our lending partner. Accordingly, the increase in the sanctioned limit is Rs. {amount}. Please e-sign the loan agreement to avail the increased sanctioned limit now.".format(
                            amount=frappe.utils.fmt_money(topup_amount)
                        ),
                        "sanction_letter": sanction_letter[0]
                        if sanction_letter
                        else None,
                    }
                )

        pending_loan_renewal_applications = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={
                "customer": customer.name,
                "status": "Loan Renewal accepted by Lender",
            },
            fields=["*"],
        )
        lra_pending_esigns = []
        if pending_loan_renewal_applications:
            for loan_renewal_application in pending_loan_renewal_applications:
                loan_renewal_application_doc = frappe.get_doc(
                    "Spark Loan Renewal Application", loan_renewal_application.name
                ).as_dict()

                loan_renewal_application_doc.top_up_amount = lms.amount_formatter(
                    loan_renewal_application_doc.top_up_amount
                )
                if loan_renewal_application_doc.sanction_letter_logs:
                    lr_sanction_letter = frappe.db.sql(
                        """select sanction_letter from `tabSanction Letter Entries` where parent = '{parent}' and renewal_application = '{name}'""".format(
                            parent=loan_renewal_application_doc.sanction_letter_logs,
                            name=loan_renewal_application_doc.name,
                        ),
                        as_dict=True,
                    )
                loan_doc = frappe.get_doc("Loan", loan_renewal_application.loan)
                items = frappe.get_all(
                    "Loan Item",
                    {"parent": loan_doc.name, "pledged_quantity": [">", 0]},
                    "*",
                )
                for i in items:
                    i["lender_approval_status"] = (
                        "Pledged" if i.type == "Shares" else "Lien"
                    )
                lra_pending_esigns.append(
                    {
                        "loan_renewal_application_doc": loan_renewal_application_doc,
                        "sanction_letter": lr_sanction_letter[0]
                        if lr_sanction_letter
                        else None,
                        "mess": "Congratulations! Your loan renewal application is being considered favourably by our lending partner. Please e-sign the loan agreement to avail the increased sanctioned limit now.",
                        "loan_items": items,
                    }
                )

        loans = frappe.get_all(
            "Loan",
            filters={"customer": customer.name},
            fields=["*"],
        )

        loan_esigns = []
        if loans:
            for loan in loans:
                loan_doc = frappe.get_doc("Loan", loan.name).as_dict()
                for i in loan_doc["items"]:
                    i["lender_approval_status"] = (
                        "Pledged" if i["type"] == "Shares" else "Lien"
                    )

                loan_esigns.append(
                    {
                        "loan_doc": loan_doc,
                        "mess": "Your ROI is updated by our lending partner. Please e-sign the loan agreement to avail the new ROI now.",
                    }
                )

        pending_esigns_list = dict(
            la_pending_esigns=la_pending_esigns,
            topup_pending_esigns=topup_pending_esigns,
            loan_renewal_esigns=lra_pending_esigns,
        )

        number_of_user_login = frappe.get_all(
            "Activity Log",
            fields=["count(status) as status_count", "status"],
            filters={
                "operation": "Login",
                "status": "Success",
                "user": customer.user,
            },
        )

        loan_customer_feedback_config = frappe.db.get_value(
            "Loan Customer",
            {"name": customer.name},
            ["name", "feedback_do_not_show_popup", "feedback_submitted"],
            as_dict=1,
        )
        show_feedback_popup = 1

        if (
            loan_customer_feedback_config
            and (
                loan_customer_feedback_config.feedback_submitted
                or loan_customer_feedback_config.feedback_do_not_show_popup
            )
        ) or number_of_user_login[0].status_count <= 10:
            show_feedback_popup = 0

        youtube_ids = []
        youtube_id_list = frappe.get_list(
            "Youtube Id", fields="youtube_id", order_by="creation desc"
        )

        if youtube_id_list:
            youtube_ids = [f["youtube_id"] for f in youtube_id_list]

        #  Profile picture URL
        profile_picture_file_url = None
        profile_picture_file_path = frappe.utils.get_files_path(
            "profile_pic/{}-profile-picture.jpeg".format(customer.name).replace(
                " ", "-"
            )
        )
        if os.path.exists(profile_picture_file_path):
            profile_picture_file_url = frappe.utils.get_url(
                "files/profile_pic/{}-profile-picture.jpeg".format(
                    customer.name
                ).replace(" ", "-")
            )

        # Count unread FCM notification
        fcm_unread_count = frappe.db.count(
            "Spark Push Notification Log",
            filters={"loan_customer": customer.name, "is_read": 0, "is_cleared": 0},
        )
        res = {
            "customer": customer,
            "user_kyc": user_kyc,
            "margin_shortfall_card": deadline_for_all_mg_shortfall,
            "total_interest_all_loans_card": total_interest_all_loans,
            "pending_esigns_list": pending_esigns_list,
            "show_feedback_popup": show_feedback_popup,
            "youtube_video_ids": youtube_ids,
            "profile_picture_file_url": profile_picture_file_url,
            "fcm_unread_count": fcm_unread_count,
        }

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def weekly_pledged_security_dashboard(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        ## sum_of_all_pledged_securities for 52 weeks
        all_loans = frappe.get_all("Loan", filters={"customer": customer.name})

        if not all_loans:
            return utils.respondWithSuccess(
                message="Please Pledge securities to see your securities performance",
                data=all_loans,
            )

        sec = []
        counter = 1
        weekly_security_amount = []
        yesterday = datetime.strptime(
            frappe.utils.today(), "%Y-%m-%d"
        ).date() - timedelta(days=1)
        offset_with_mod = (yesterday.weekday() - 4) % 7
        last_friday = yesterday - timedelta(days=offset_with_mod)

        all_loan_items = frappe.get_all(
            "Loan Item",
            filters={
                "parent": ["in", [loan.name for loan in all_loans]],
                "pledged_quantity": [">", 0],
            },
            fields=["isin", "sum(pledged_quantity) as total_pledged_qty"],
            group_by="isin",
        )
        all_isin_list = [i.isin for i in all_loan_items]

        while counter <= 52:
            sec.append({"yesterday": yesterday, "last_friday": last_friday})
            security_price_list = frappe.db.sql(
                """select security, price, time
				from `tabSecurity Price`
				where name in (select max(name) from `tabSecurity Price` where security  IN {}
				and `tabSecurity Price`.time like '%{}%'
                group by security
				order by modified desc)""".format(
                    lms.convert_list_to_tuple_string(all_isin_list),
                    yesterday if counter == 1 else last_friday,
                ),
                as_dict=1,
            )

            total = sum(
                [
                    i.price * j.total_pledged_qty
                    for j in all_loan_items
                    for i in security_price_list
                    if i.security == j.isin
                ]
            )

            if counter != 1:
                last_friday += timedelta(days=-7)

            weekly_security_amount.append(
                {
                    "week": counter,
                    "weekly_amount_for_all_loans": round(total, 2) if total else 0.0,
                }
            )
            counter += 1
        weekly_security_amount.sort(key=lambda item: (item["week"]), reverse=True)
        return utils.respondWithSuccess(data=weekly_security_amount)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def get_profile_set_alerts(**kwargs):
    try:
        utils.validator.validate_http_method("GET")
        user = lms.__user()
        customer = lms.__customer(user.name)

        data = utils.validator.validate(
            kwargs,
            {
                "is_for_alerts": "decimal|between:0,1",
                "percentage": "decimal|min:0",
                "amount": "decimal|min:0",
            },
        )

        if isinstance(data.get("is_for_alerts"), str):
            data["is_for_alerts"] = int(data.get("is_for_alerts"))

        # user_kyc details
        try:
            user_kyc = lms.__user_kyc(user.email)
            user_kyc.pan_no = lms.user_details_hashing(user_kyc.pan_no)
            for i in user_kyc.bank_account:
                i.account_number = lms.user_details_hashing(i.account_number)
        except UserKYCNotFoundException:
            user_kyc = None

        # last login details
        last_login_time = None
        last_login = frappe.get_all(
            "Activity Log",
            fields=["*"],
            filters={"operation": "Login", "status": "Success", "user": user.email},
            order_by="creation desc",
        )
        if len(last_login) > 1:
            last_login_time = (last_login[1].creation).strftime("%Y-%m-%d %H:%M:%S")

        #  Profile picture URL
        profile_picture_file_url = None
        profile_picture_file_path = frappe.utils.get_files_path(
            "profile_pic/{}-profile-picture.jpeg".format(customer.name).replace(
                " ", "-"
            )
        )
        if os.path.exists(profile_picture_file_path):
            profile_picture_file_url = frappe.utils.get_url(
                "files/profile_pic/{}-profile-picture.jpeg".format(
                    customer.name
                ).replace(" ", "-")
            )

        # alerts percentage and amount save in doctype
        if (
            data.get("is_for_alerts")
            and not data.get("percentage")
            and not data.get("amount")
        ):
            raise lms.exceptions.RespondFailureException(
                _("Please select Amount or Percentage for setting Alerts.")
            )

        elif (
            data.get("is_for_alerts") and data.get("percentage") and data.get("amount")
        ):
            raise lms.exceptions.RespondFailureException(
                _("Please choose one between Amount or Percentage for setting Alerts.")
            )

        elif data.get("is_for_alerts") and data.get("percentage"):
            customer.alerts_based_on_percentage = data.get("percentage")
            # if percentage given then amount should be zero
            customer.alerts_based_on_amount = 0
            customer.save(ignore_permissions=True)
            frappe.db.commit()

        elif data.get("is_for_alerts") and data.get("amount"):
            customer.alerts_based_on_amount = data.get("amount")
            # if amount given then percentage should be zero
            customer.alerts_based_on_percentage = 0
            customer.save(ignore_permissions=True)
            frappe.db.commit()

        loan_application = frappe.get_all(
            "Loan Application",
            filters={"customer": customer.name, "application_type": "New Loan"},
            fields=["*"],
        )
        loan = frappe.get_all(
            "Loan",
            filters={"customer": customer.name},
            fields=["*"],
        )
        loan_name = ""
        if loan_application:
            status = loan_application[0].status
            instrument_type = loan_application[0].instrument_type
            pledgor_boid = loan_application[0].pledgor_boid
            if status == "Approved" and loan:
                loan_name = loan[0].name
            else:
                status = "Pending"
        else:
            status = ""
            instrument_type = ""
            pledgor_boid = ""
        res = {
            "customer_details": customer,
            "loan_application_status": status,
            "loan_name": loan_name,
            "instrument_type": instrument_type,
            "pledgor_boid": pledgor_boid,
            "user_kyc": user_kyc,
            "last_login": last_login_time,
            "profile_picture_file_url": profile_picture_file_url,
        }

        return utils.respondWithSuccess(data=res)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def update_profile_pic_and_pin(**kwargs):
    try:
        # validation
        utils.validator.validate_http_method("POST")
        user = lms.__user()
        customer = lms.__customer(user.name)

        data = utils.validator.validate(
            kwargs,
            {
                "is_for_profile_pic": "decimal|between:0,1",
                "image": "",
                "is_for_update_pin": "decimal|between:0,1",
                "old_pin": ["decimal", utils.validator.rules.LengthRule(4)],
                "new_pin": ["decimal", utils.validator.rules.LengthRule(4)],
                "retype_pin": ["decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        if isinstance(data.get("is_for_profile_pic"), str):
            data["is_for_profile_pic"] = int(data.get("is_for_profile_pic"))

        if isinstance(data.get("image"), str):
            data["image"] = bytes(data.get("image"), encoding="utf8")

        if isinstance(data.get("is_for_update_pin"), str):
            data["is_for_update_pin"] = int(data.get("is_for_update_pin"))

        if data.get("is_for_profile_pic") and data.get("image"):
            tnc_dir_path = frappe.utils.get_files_path("profile_pic")

            if not os.path.exists(tnc_dir_path):
                os.mkdir(tnc_dir_path)

            profile_picture_file = "profile_pic/{}-profile-picture.jpeg".format(
                customer.name
            ).replace(" ", "-")

            image_path = frappe.utils.get_files_path(profile_picture_file)
            if os.path.exists(image_path):
                os.remove(image_path)

            profile_picture_file = "profile_pic/{}-profile-picture.jpeg".format(
                customer.name
            ).replace(" ", "-")

            profile_picture_file_path = frappe.utils.get_files_path(
                profile_picture_file
            )

            image_decode = base64.decodestring(data.get("image"))
            image_file = open(profile_picture_file_path, "wb").write(image_decode)

            profile_picture_file_url = frappe.utils.get_url(
                "files/profile_pic/{}-profile-picture.jpeg".format(
                    customer.name
                ).replace(" ", "-")
            )
            return utils.respondWithSuccess(
                data={"profile_picture_file_url": profile_picture_file_url}
            )

        elif data.get("is_for_profile_pic") and not data.get("image"):
            raise lms.exceptions.RespondFailureException(_("Please upload image."))

        if (
            data.get("is_for_update_pin")
            and data.get("old_pin")
            and data.get("new_pin")
            and data.get("retype_pin")
        ):
            try:
                # returns user in correct case
                old_pass_check = check_password(
                    frappe.session.user, data.get("old_pin")
                )
            except frappe.AuthenticationError:
                raise lms.exceptions.RespondFailureException(_("Invalid current pin."))

            if old_pass_check:
                if data.get("retype_pin") == data.get("new_pin") and data.get(
                    "old_pin"
                ) != data.get("new_pin"):
                    # update pin
                    update_password(frappe.session.user, data.get("retype_pin"))
                    frappe.db.commit()
                elif data.get("old_pin") == data.get("new_pin"):
                    raise lms.exceptions.RespondFailureException(
                        _("New pin cannot be same as old pin.")
                    )
                else:
                    raise lms.exceptions.RespondFailureException(
                        _("Retyped pin does not match with new pin")
                    )

            return utils.respondWithSuccess(
                message=frappe._("Your pin has been changed successfully!")
            )

        elif data.get("is_for_update_pin") and (
            not data.get("old_pin") or not data.get("new_pin")
        ):
            raise lms.exceptions.RespondFailureException(
                _("Please Enter old pin and new pin.")
            )

    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def check_eligible_limit(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs, {"lender": "", "search": "", "instrument_type": ""}
        )

        reg = lms.regex_special_characters(
            search=data.get("lender") or "" + data.get("instrument_type") or ""
        )
        search_reg = lms.regex_special_characters(
            search=data.get("search"), regex=re.compile("[@!#$%_^&*<>?/\|}{~`]")
        )
        if reg or search_reg:
            raise lms.exceptions.FailureException(_("Special Charaters not allowed."))

        if not data.get("lender"):
            data["lender"] = frappe.get_last_doc("Lender").name

        if not data.get("instrument_type"):
            data["instrument_type"] = "Shares"

        eligible_limit_list = frappe.db.sql(
            """
			SELECT
			als.security_name as Scrip_Name, als.eligible_percentage, als.lender, als.category_name as Category, s.price as Price
			FROM `tabAllowed Security` als
			LEFT JOIN `tabSecurity` s
			ON als.isin = s.isin
			where als.lender = '{}' and
            als.instrument_type = '{}'
            and s.price > 0
			and als.security_name like '%{}%'
            order by als.security_name;
			""".format(
                data.get("lender"), data.get("instrument_type"), data.get("search")
            ),
            as_dict=1,
        )

        if not eligible_limit_list:
            raise lms.exceptions.NotFoundException(_("No Record Found"))

        list = map(lambda item: dict(item, Is_Eligible=True), eligible_limit_list)

        return utils.respondWithSuccess(data=list)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def all_lenders_list(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        try:
            user_kyc = lms.__user_kyc()
            user_kyc = lms.user_kyc_hashing(user_kyc)
        except UserKYCNotFoundException:
            user_kyc = None

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        all_lenders = []
        lenders = frappe.get_all("Lender", order_by="creation asc")
        for lender in lenders:
            query = [
                "Level {}".format(i.level)
                for i in frappe.db.sql(
                    "select idx as level from `tabConcentration Rule` where parent = '{}' order by idx asc".format(
                        lender.name
                    ),
                    as_dict=True,
                )
            ]
            all_lenders.append({"name": lender.name, "levels": query})
        return utils.respondWithSuccess(data=all_lenders)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def feedback(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "do_not_show_again": "decimal|between:0,1",
                "bulls_eye": "decimal|between:0,1",
                "can_do_better": "decimal|between:0,1",
                "related_to_user_experience": "decimal|between:0,1",
                "related_to_functionality": "decimal|between:0,1",
                "others": "decimal|between:0,1",
                "comment": "",
                "from_more_menu": "decimal|between:0,1",
            },
        )

        customer = lms.__customer()
        reg = lms.regex_special_characters(search=data.get("comment"))
        if reg:
            raise lms.exceptions.FailureException(_("Special Charaters not allowed."))

        if isinstance(data.get("do_not_show_again"), str):
            data["do_not_show_again"] = int(data.get("do_not_show_again"))

        if isinstance(data.get("bulls_eye"), str):
            data["bulls_eye"] = int(data.get("bulls_eye"))

        if isinstance(data.get("can_do_better"), str):
            data["can_do_better"] = int(data.get("can_do_better"))

        if isinstance(data.get("related_to_user_experience"), str):
            data["related_to_user_experience"] = int(
                data.get("related_to_user_experience")
            )

        if isinstance(data.get("related_to_functionality"), str):
            data["related_to_functionality"] = int(data.get("related_to_functionality"))

        if isinstance(data.get("others"), str):
            data["others"] = int(data.get("others"))

        if isinstance(data.get("from_more_menu"), str):
            data["from_more_menu"] = int(data.get("from_more_menu"))

        if not data.get("do_not_show_again"):
            if (data.get("bulls_eye") and data.get("can_do_better")) or (
                not data.get("bulls_eye") and not data.get("can_do_better")
            ):
                raise lms.exceptions.RespondFailureException(
                    _("Please select atleast one option.")
                )

            if (
                data.get("can_do_better")
                and not data.get("related_to_user_experience")
                and not data.get("related_to_functionality")
                and not data.get("others")
            ):
                raise lms.exceptions.RespondFailureException(
                    _("Please select atleast one from below options.")
                )

            if not data.get("comment") or data.get("comment").isspace():
                raise lms.exceptions.RespondWithFailureException(
                    _("Please write your suggestions to us.")
                )

        number_of_user_login = frappe.get_all(
            "Activity Log",
            fields=["count(status) as status_count", "status"],
            filters={
                "operation": "Login",
                "status": "Success",
                "user": customer.user,
            },
        )

        loan_customer_feedback_config = frappe.db.get_value(
            "Loan Customer",
            {"name": customer.name},
            ["name", "feedback_do_not_show_popup", "feedback_submitted"],
            as_dict=1,
        )

        if data.get("do_not_show_again"):
            customer.feedback_do_not_show_popup = 1
            customer.save(ignore_permissions=True)
            frappe.db.commit()
            return utils.respondWithSuccess(message=frappe._("successfully saved."))

        elif number_of_user_login[0].status_count > 10 or data.get("from_more_menu"):
            feedback_doc = frappe.get_doc(
                {
                    "doctype": "Spark Feedback",
                    "customer": customer.name,
                    "sparkloans_have_hit_the_bulls_eye": data.get("bulls_eye"),
                    "sparkloans_can_do_better": data.get("can_do_better"),
                    "related_to_user_experience": data.get(
                        "related_to_user_experience"
                    ),
                    "related_to_functionality": data.get("related_to_functionality"),
                    "others": data.get("others"),
                    "comment": data.get("comment").strip(),
                }
            )
            feedback_doc.insert(ignore_permissions=True)
            if (
                loan_customer_feedback_config
                and not loan_customer_feedback_config["feedback_submitted"]
            ):
                customer.feedback_submitted = 1
                customer.save(ignore_permissions=True)

            frappe.db.commit()

            return utils.respondWithSuccess(
                message=frappe._("Feedback submitted successfully.")
            )

        else:
            raise lms.exceptions.RespondFailureException(
                _("Oops something went wrong.")
            )

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def loan_summary_dashboard(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        all_loans = frappe.get_all(
            "Loan", filters={"customer": customer.name}, fields=["*"]
        )

        margin_shortfall_and_interest_loans = (
            lms.user.margin_shortfall_and_interest_loans(customer)
        )
        loan_name = [loan["name"] for loan in margin_shortfall_and_interest_loans[0]]

        actionable_loan = []
        mg_interest_loan = []
        sell_collateral_topup_and_unpledge_list = []
        sell_collateral_list = []
        unpledge_list = []
        topup_list = []
        increase_loan_list = []

        mg_interest_loan.extend(margin_shortfall_and_interest_loans[0])
        mg_interest_loan.extend(
            [
                loan
                for loan in margin_shortfall_and_interest_loans[1]
                if loan["name"] not in loan_name
            ]
        )
        for loans in mg_interest_loan:
            actionable_loan.append(
                {
                    "name": loans["name"],
                    "drawing_power": loans["drawing_power"],
                    "drawing_power_str": loans["drawing_power_str"],
                    "balance": loans["balance"],
                    "balance_str": loans["balance_str"],
                    "creation": loans["creation"],
                }
            )

        under_process_la = frappe.get_all(
            "Loan Application",
            filters={
                "customer": customer.name,
                "status": ["not IN", ["Approved", "Rejected", "Pledge Failure"]],
                "pledge_status": ["!=", "Failure"],
            },
            fields=["name", "status", "creation"],
            order_by="creation desc",
        )

        under_process_lr = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={
                "customer": customer.name,
                "status": ["not IN", ["Approved", "Rejected", "Pending"]],
            },
            fields=["name", "status", "creation"],
            order_by="creation desc",
        )

        ## Active loans ##
        active_loans = frappe.get_all(
            "Loan",
            filters={
                "customer": customer.name,
                "name": ["not in", [list["name"] for list in actionable_loan]],
            },
            fields=[
                "name",
                "drawing_power",
                "drawing_power_str",
                "balance",
                "balance_str",
                "creation",
            ],
            order_by="creation desc",
        )
        for loan in all_loans:
            loan = frappe.get_doc("Loan", loan.name)
            # Sell Collateral
            sell_collateral_application_exist = frappe.get_all(
                "Sell Collateral Application",
                filters={"loan": loan.name, "status": "Pending"},
                fields=[
                    "name",
                    "creation",
                    "modified",
                    "modified_by",
                    "owner",
                    "docstatus",
                    "parent",
                    "parentfield",
                    "parenttype",
                    "idx",
                    "loan",
                    "total_collateral_value",
                    "lender",
                    "customer",
                    "selling_collateral_value",
                    "amended_from",
                    "status",
                    "workflow_state",
                    "loan_margin_shortfall",
                ],
                order_by="creation desc",
                page_length=1,
            )
            if sell_collateral_application_exist:
                sell_collateral_application_exist[0]["items"] = frappe.get_all(
                    "Sell Collateral Application Item",
                    filters={"parent": sell_collateral_application_exist[0].name},
                    fields=["*"],
                )

                sell_collateral_topup_and_unpledge_list.append(
                    {
                        "loan_name": loan.name,
                        "creation": sell_collateral_application_exist[0].creation,
                        "sell_collateral_available": sell_collateral_application_exist[
                            0
                        ],
                        "unpledge_application_available": None,
                        "unpledge_msg_while_margin_shortfall": None,
                        "unpledge": None,
                        "top_up_amount": 0.0,
                        "existing_topup_application": None,
                    }
                )
            loan_margin_shortfall = loan.get_margin_shortfall()
            if loan_margin_shortfall.get("__islocal", None):
                loan_margin_shortfall = None

            is_sell_triggered = 0
            if loan_margin_shortfall:
                if loan_margin_shortfall.status == "Sell Triggered":
                    is_sell_triggered = 1

            sell_collateral_list.append(
                {
                    "loan_name": loan.name,
                    "sell_collateral_available": sell_collateral_application_exist[0]
                    if sell_collateral_application_exist
                    else None,
                    "is_sell_triggered": is_sell_triggered,
                }
            )

            unpledge_application_exist = frappe.get_all(
                "Unpledge Application",
                filters={"loan": loan.name, "status": "Pending"},
                fields=[
                    "name",
                    "creation",
                    "modified",
                    "modified_by",
                    "owner",
                    "docstatus",
                    "parent",
                    "parentfield",
                    "parenttype",
                    "idx",
                    "loan",
                    "total_collateral_value",
                    "lender",
                    "customer",
                    "unpledge_collateral_value",
                    "amended_from",
                    "status",
                    "workflow_state",
                ],
                order_by="creation desc",
                page_length=1,
            )
            if unpledge_application_exist:
                unpledge_application_exist[0]["items"] = frappe.get_all(
                    "Unpledge Application Item",
                    filters={"parent": unpledge_application_exist[0].name},
                    fields=["*"],
                )

                sell_collateral_topup_and_unpledge_list.append(
                    {
                        "loan_name": loan.name,
                        "creation": unpledge_application_exist[0].creation,
                        "unpledge_application_available": unpledge_application_exist[0],
                        "unpledge_msg_while_margin_shortfall": None,
                        "unpledge": None,
                        "sell_collateral_available": None,
                        "top_up_amount": 0.0,
                        "existing_topup_application": None,
                    }
                )
            else:
                msg_type = ["unpledge", "pledged securities"]
                if loan.instrument_type == "Mutual Fund":
                    msg_type = ["revoke", "liened schemes"]
                unpledge_list.append(
                    {
                        "loan_name": loan.name,
                        "unpledge_application_available": None,
                        "unpledge_msg_while_margin_shortfall": """OOPS! Dear {}, It seems you have a margin shortfall. You cannot {} any of the {} until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                            loan.get_customer().first_name, msg_type[0], msg_type[1]
                        )
                        if loan_margin_shortfall
                        else None,
                        "unpledge": None
                        if unpledge_application_exist or loan_margin_shortfall
                        else None,
                    }
                )

            existing_topup_application = frappe.get_all(
                "Top up Application",
                filters={
                    "loan": loan.name,
                    "status": ["not IN", ["Approved", "Rejected"]],
                },
                fields=["*"],
            )

            if existing_topup_application:
                sell_collateral_topup_and_unpledge_list.append(
                    {
                        "loan_name": loan.name,
                        "creation": existing_topup_application[0].creation,
                        "top_up_amount": 0.0,
                        "existing_topup_application": existing_topup_application[0],
                        "unpledge_application_available": None,
                        "unpledge_msg_while_margin_shortfall": None,
                        "unpledge": None,
                        "sell_collateral_available": None,
                    }
                )

            else:
                topup = loan.max_topup_amount()
                if topup:
                    topup_list.append({"loan_name": loan.name, "top_up_amount": topup})

            # Increase Loan
            existing_loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "loan": loan.name,
                    "customer": loan.customer,
                    "status": ["not IN", ["Approved", "Rejected", "Pledge Failure"]],
                },
                fields=["count(name) as in_process"],
            )

            increase_loan_list.append(
                {
                    "loan_name": loan.name,
                    "increase_loan_available": 1
                    if existing_loan_application[0]["in_process"] == 0
                    else None,
                }
            )

        sell_collateral_topup_and_unpledge_list.sort(
            key=lambda item: (item["creation"]), reverse=True
        )
        sell_collateral_list.sort(key=lambda item: (item["loan_name"]), reverse=True)
        unpledge_list.sort(key=lambda item: (item["loan_name"]), reverse=True)
        topup_list.sort(key=lambda item: (item["loan_name"]), reverse=True)
        increase_loan_list.sort(key=lambda item: (item["loan_name"]), reverse=True)

        version_details = frappe.get_all(
            "Spark App Version",
            filters={"is_live": 1},
            fields=["*"],
            order_by="release_date desc",
            page_length=1,
        )
        if not version_details:
            version_details = ["No Record found"]

        instrument_type = ""
        scheme_type = ""
        if under_process_la:
            instrument_type = frappe.get_doc(
                "Loan Application", under_process_la[0].name
            ).instrument_type
            if instrument_type == "Mutual Fund":
                scheme_type = frappe.get_doc(
                    "Loan Application", under_process_la[0].name
                ).scheme_type
            for la in under_process_la:
                la_doc = frappe.get_doc("Loan Application", la.name)
                if (
                    la_doc.instrument_type == "Mutual Fund"
                    and "pledge" in la_doc.status.lower()
                ):
                    scheme_type = la_doc.scheme_type
                    la.status = la_doc.status.lower().replace("pledge", "Lien")

        elif all_loans:
            instrument_type = frappe.get_doc("Loan", all_loans[0].name).instrument_type
            if instrument_type == "Mutual Fund":
                scheme_type = frappe.get_doc("Loan", all_loans[0].name).scheme_type

        loan_renewal_doc_list = []
        sl_letter = ""
        for loan in all_loans:
            loan_renewal_list = frappe.get_all(
                "Spark Loan Renewal Application",
                filters={"loan": loan.name, "status": ["!=", "Rejected"]},
                fields=["name"],
            )
            top_up_application = frappe.get_all(
                "Top up Application",
                filters={
                    "loan": loan.name,
                    "status": ["NOT IN", ["Approved", "Rejected"]],
                },
                fields=["name"],
            )

            loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "loan": loan.name,
                    "application_type": [
                        "IN",
                        ["Increase Loan", "Pledge More", "Margin Shortfall"],
                    ],
                    "status": ["Not IN", ["Approved", "Rejected"]],
                },
                fields=["name"],
            )
            user_kyc_pending = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                    "kyc_status": "Pending",
                },
                fields=["*"],
            )
            if top_up_application or loan_application:
                action_status = "Pending"
            else:
                action_status = ""
            if loan_renewal_list:
                loan_renewal_doc = frappe.get_doc(
                    "Spark Loan Renewal Application", loan_renewal_list[0]
                )
                loan_expiry = datetime.combine(loan.expiry_date, time.min)
                date_7after_expiry = loan_expiry + timedelta(days=8)
                is_expired_date = datetime.strptime(
                    str(loan.expiry_date), "%Y-%m-%d"
                ) + timedelta(days=14)
                date_1 = 0
                extended_two_days = 0
                if loan_renewal_doc.kyc_approval_date:
                    date_1 = loan_renewal_doc.kyc_approval_date.date()

                    extended_two_days = loan_renewal_doc.kyc_approval_date + timedelta(
                        days=2
                    )
                if (
                    frappe.utils.now_datetime().date() > loan.expiry_date
                    and frappe.utils.now_datetime().date()
                    <= (loan.expiry_date + timedelta(days=7))
                    and loan_renewal_doc.status != "Approved"
                ):
                    seconds = abs(
                        date_7after_expiry - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )

                elif (
                    frappe.utils.now_datetime().date()
                    > (loan.expiry_date + timedelta(days=7))
                    and frappe.utils.now_datetime().date()
                    <= (loan.expiry_date + timedelta(days=14))
                    and loan_renewal_doc.status != "Approved"
                    and user_kyc_pending
                ):
                    seconds = abs(
                        (date_7after_expiry + timedelta(days=7))
                        - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )
                elif (
                    date_1
                    and extended_two_days
                    and date_1 > is_expired_date.date()
                    and frappe.utils.now_datetime() < extended_two_days
                ):
                    seconds = abs(
                        extended_two_days - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )

                else:
                    seconds = 0
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )
                loan_renewal_doc.time_remaining = renewal_timer
                loan_renewal_doc.action_status = action_status

                str_exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").strftime(
                    "%d-%m-%Y"
                )
                str_exp = str_exp.replace("-", "/")
                loan_renewal_doc.expiry_date = str_exp
                if loan.name in ["SL000004", "SL000026"]:
                    str_exp = datetime.strptime(
                        str(frappe.utils.now_datetime().date() + timedelta(6)),
                        "%Y-%m-%d",
                    ).strftime("%d/%m/%Y")
                    loan_renewal_doc.expiry_date = str_exp

                loan_renewal_doc_list.append(loan_renewal_doc)
            if loan.sl_cial_entries:
                loan_sanctioned_letter_list = frappe.get_all(
                    "Sanction Letter and CIAL Log",
                    filters={"name": loan.sl_cial_entries},
                    fields=["*"],
                )
                sanction_letter_list = frappe.get_doc(
                    "Sanction Letter and CIAL Log", loan_sanctioned_letter_list[0].name
                )
                for i in sanction_letter_list.sl_table:
                    sl_letter = frappe.utils.get_url(i.sanction_letter)

        res = {
            "sell_collateral_topup_and_unpledge_list": sell_collateral_topup_and_unpledge_list,
            "actionable_loan": actionable_loan,
            "under_process_la": under_process_la,
            "under_process_loan_renewal_app": under_process_lr,
            "active_loans": active_loans,
            "sell_collateral_list": sell_collateral_list,
            "unpledge_list": unpledge_list,
            "topup_list": topup_list,
            "increase_loan_list": increase_loan_list,
            "instrument_type": instrument_type,
            "scheme_type": scheme_type,
            "loan_renewal_application": loan_renewal_doc_list,
            "sanctioned_letter": sl_letter,
            "version_details": version_details[0],
        }

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


def margin_shortfall_and_interest_loans(customer):
    all_mgloans = frappe.db.sql(
        """select loan.name, loan.drawing_power, loan.drawing_power_str, loan.balance, loan.balance_str, loan.creation, IFNULL(mrgloan.shortfall_percentage, 0.0) as shortfall_percentage, IFNULL(mrgloan.shortfall, 0.0) as shortfall, mrgloan.status as status
    from `tabLoan` as loan
    left join `tabLoan Margin Shortfall` as mrgloan
    on loan.name = mrgloan.loan
    where loan.customer = '{}'
    and (mrgloan.status = "Pending" or mrgloan.status = "Sell Triggered" or mrgloan.status = "Request Pending")
    and shortfall_percentage > 0.0
    group by loan.name
    order by loan.creation desc""".format(
            customer.name
        ),
        as_dict=1,
    )

    all_interest_loans = frappe.db.sql(
        """select loan.name, loan.drawing_power, loan.drawing_power_str, loan.balance, loan.balance_str, loan.creation, sum(loantx.unpaid_interest) as interest_amount
    from `tabLoan` as loan
    left join `tabLoan Transaction` as loantx
    on loan.name = loantx.loan
    where loan.customer = '{}'
    and loantx.transaction_type in ('Interest','Additional Interest','Penal Interest')
    and loantx.unpaid_interest > 0
    group by loan.name
    order by loan.creation desc""".format(
            customer.name
        ),
        as_dict=1,
    )

    return all_mgloans, all_interest_loans


@frappe.whitelist()
def otp_for_testing(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(kwargs, {"otp_type": "required"})

        if data.get("otp_type") not in [
            "OTP",
            "Pledge OTP",
            "Withdraw OTP",
            "Unpledge OTP",
            "Sell Collateral OTP",
            "Forgot Pin OTP",
        ]:
            raise lms.exceptions.RespondFailureException(_("Incorrect OTP type."))

        customer = lms.__customer()

        if data.get("otp_type") in ["OTP", "Withdraw OTP", "Sell Collateral OTP"]:
            entity = customer.phone
        elif data.get("otp_type") == "Forgot Pin OTP":
            entity = customer.user
        else:
            entity = lms.__user_kyc().mobile_number

        tester = frappe.db.sql(
            "select c.user,c.full_name from `tabLoan Customer` as c left join `tabHas Role` as r on c.user=r.parent where role='Spark Tester' and r.parent='{}'".format(
                customer.user
            ),
            as_dict=1,
        )

        if not tester:
            # Unauthorized user
            raise lms.exceptions.UnauthorizedException(_("Unauthorized User"))

        if tester:
            # Mark old token as Used
            old_token_name = frappe.get_all(
                "User Token",
                filters={
                    "entity": entity,
                    "token_type": "{}".format(data.get("otp_type")),
                },
                order_by="creation desc",
                fields=["*"],
            )
            if old_token_name:
                old_token = frappe.get_doc("User Token", old_token_name[0].name)
                lms.token_mark_as_used(old_token)

            # Create New token
            lms.create_user_token(
                entity=entity,
                token_type="{}".format(data.get("otp_type")),
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()

            # Fetch New token
            token = frappe.get_all(
                "User Token",
                filters={
                    "entity": entity,
                    "token_type": "{}".format(data.get("otp_type")),
                    "used": 0,
                },
                order_by="creation desc",
                fields=["token as OTP"],
                page_length=1,
            )

            return utils.respondWithSuccess(data=token[0] if token else None)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def push_notification_list(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        all_notifications = frappe.db.sql(
            "select name, title, loan_customer, loan, screen_to_open, notification_id, notification_type, click_action, DATE_FORMAT(time, '%d %b at %h:%i %p') as time, message, is_cleared, is_read from `tabSpark Push Notification Log` where loan_customer='{loan_customer}' and is_cleared=0 order by creation desc".format(
                loan_customer=customer.name
            ),
            as_dict=True,
        )

        if not all_notifications:
            return utils.respondWithSuccess(message="No notification found")

        return utils.respondWithSuccess(data=all_notifications)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def read_or_clear_notifications(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "is_for_read": "decimal|between:0,1",
                "is_for_clear": "decimal|between:0,1",
                "notification_name": "",
            },
        )

        if isinstance(data.get("is_for_read"), str):
            data["is_for_read"] = int(data.get("is_for_read"))

        if isinstance(data.get("is_for_clear"), str):
            data["is_for_clear"] = int(data.get("is_for_clear"))

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        if data.get("is_for_read") and data.get("is_for_clear"):
            raise lms.exceptions.ForbiddenException(
                _("Can not use both option at once, please use one.")
            )

        if data.get("is_for_read") and not data.get("notification_name"):
            raise lms.exceptions.RespondFailureException(
                _("Notification name field empty.")
            )

        if data.get("is_for_clear") and not data.get("notification_name"):
            notification_name = frappe.get_all(
                "Spark Push Notification Log",
                filters={"loan_customer": customer.name, "is_cleared": 0},
            )
            for fcm in notification_name:
                fcm_log = frappe.get_doc("Spark Push Notification Log", fcm["name"])
                fcm_log.is_cleared = 1
                fcm_log.save(ignore_permissions=True)
                frappe.db.commit()

        if data.get("notification_name"):
            fcm_log = frappe.get_doc(
                "Spark Push Notification Log", data.get("notification_name")
            )
            if fcm_log.loan_customer != customer.name:
                raise lms.exceptions.ForbiddenException(
                    _("Notification doesnt belong to this customer.")
                )

            if data.get("is_for_clear"):
                if fcm_log.is_cleared == 0:
                    fcm_log.is_cleared = 1
                    fcm_log.save(ignore_permissions=True)
                    frappe.db.commit()
                else:
                    raise lms.exceptions.RespondFailureException(
                        _("Notification not found.")
                    )
            if data.get("is_for_read"):
                if fcm_log.is_read == 0:
                    fcm_log.is_read = 1
                    fcm_log.save(ignore_permissions=True)
                    frappe.db.commit()

        return utils.respondWithSuccess()

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def contact_us(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(kwargs, {"message": "required"})

        if not data.get("message") or data.get("message").isspace():
            raise lms.exceptions.RespondWithFailureException(
                _("Please write your query to us.")
            )

        try:
            user = lms.__user()
        except UserNotFoundException:
            user = None

        if user and data.get("message"):
            recipients = frappe.get_single("Contact Us Settings").forward_to_email
            from frappe.model.naming import getseries

            subject = "Contact us Request – " + getseries("Contact us Request –", 3)
            frappe.db.commit()

            message = "{mess}<br><br>From - {name},<br>Email id - {email},<br>Mobile number - {phone},<br>Customer id - {cust}".format(
                mess=data.get("message").strip(),
                name=user.full_name,
                email=user.email,
                phone=lms.__customer().phone,
                cust=lms.__customer().name,
            )

            frappe.get_doc(
                dict(
                    doctype="Communication",
                    sender=user.email,
                    subject=_("New Message from Website Contact Page"),
                    sent_or_received="Received",
                    content=message,
                    status="Open",
                )
            ).insert(ignore_permissions=True)

            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[recipients],
                sender=None,
                subject=subject,
                message=message.replace("\n", "<br>"),
            )

        return utils.respondWithSuccess()
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def spark_demat_account(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {"demat": ""},
        )

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))
        if not data.get("demat") or (
            type(data.get("demat")) is not dict
            or "list" not in data.get("demat").keys()
        ):
            raise utils.exceptions.ValidationException(
                {"demat": {"required": frappe._("Demat required.")}}
            )
        if type(data.get("demat").get("list")) is not list:
            raise utils.exceptions.ValidationException(
                {"demat": {"required": frappe._("list should be in list format.")}}
            )
        frappe.delete_doc(
            "Spark Demat Account",
            frappe.get_all(
                "Spark Demat Account",
                {"customer": customer.name},
                pluck="name",
            ),
            ignore_permissions=True,
        )
        demat = data.get("demat").get("list")
        demat_list = True
        for i in demat:
            if type(i) is not dict:
                demat_list = False
                message = frappe._("Items should be in dictionary format")
                break

            keys = i.keys()
            if (
                "depository" not in keys
                or "dpid" not in keys
                or "client_id" not in keys
            ):
                demat_list = False
                message = frappe._("depository or dpid or client_id not present")
                break

        if not demat_list:
            raise utils.exceptions.ValidationException({"dlist": {"required": message}})

        # field alphanumeric validation
        for i in demat:
            keys = i.values()
            for i in keys:
                i = str(i)
                reg = lms.regex_special_characters(search=i)
                if reg:
                    raise lms.exceptions.FailureException(
                        _("Special Charaters not allowed.")
                    )
        for i in demat:
            frappe.get_doc(
                {
                    "doctype": "Spark Demat Account",
                    "customer": customer.name,
                    "depository": i["depository"],
                    "dpid": i["dpid"],
                    "is_choice": i["is_choice"],
                    "client_id": i["client_id"],
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()
        return utils.respondWithSuccess(
            message="Your details have been successfully saved"
        )
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def update_mycams_email(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {"email": ["required"]},
        )
        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        # email validation
        # email_regex = r"^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,}$"
        email_regex = (
            r"^([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})"
        )
        if re.search(email_regex, data.get("email")) is None or (
            len(data.get("email").split("@")) > 2
        ):
            raise lms.exceptions.FailureException(_("Please enter valid email ID"))
        customer = lms.__customer()
        customer.mycams_email_id = data.get("email").strip()
        customer.save(ignore_permissions=True)
        frappe.db.commit()
        return utils.respondWithSuccess(data=customer)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        frappe.log_error(
            message=frappe.get_traceback() + json.dumps(data),
            title=_("Loan Customer - MyCams Email Update Error"),
        )
        return e.respond()


@frappe.whitelist()
def get_bank_ifsc_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"ifsc": ""})
        if not data.get("ifsc"):
            raise lms.exceptions.FailureException(_("Field is empty"))

        is_alphanumeric = lms.regex_special_characters(
            search=data.get("ifsc"), regex=re.compile("^[a-zA-Z0-9]*$")
        )

        if not is_alphanumeric:
            raise lms.exceptions.FailureException(_("Only alphanumeric allowed."))

        details = lms.ifsc_details(data.get("ifsc"))

        if not details:
            return utils.respondWithSuccess(message="Record not found.")

        return utils.respondWithSuccess(data=details)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def penny_create_contact(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        # check user
        try:
            user = lms.__user()
        except UserNotFoundException:
            raise lms.exceptions.NotFoundException(_("User not found"))

        if user:
            contact_id = lms.penny_call_create_contact(user.name)

        if contact_id.get("message") == "User KYC not found":
            raise lms.exceptions.NotFoundException(_("User KYC not found"))
        elif contact_id.get("message") == "Customer not found":
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        elif contact_id.get("message") == "failed":
            raise lms.exceptions.RespondWithFailureException(_("failed"))
        elif (
            contact_id.get("message")
            == "Penny Drop Create contact Error - Razorpay Key Secret Missing"
        ):
            raise lms.exceptions.FailureException(
                _("Penny Drop Create contact Error - Razorpay Key Secret Missing")
            )
        else:
            customer = lms.__customer(user.name)
            if not customer:
                raise lms.exceptions.NotFoundException(_("Customer not found"))
            try:
                user_kyc = lms.__user_kyc(user.name)
            except UserKYCNotFoundException:
                raise lms.exceptions.NotFoundException(_("User KYC not found"))

            user_kyc.razorpay_contact_id = contact_id.get("message")
            user_kyc.save(ignore_permissions=True)
            frappe.db.commit()
            return utils.respondWithSuccess(message=frappe._("success"))

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        frappe.log_error(
            title="Penny Drop Create contact Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create contact Error: "
            + str(e.args),
        )
        return e.respond()


@frappe.whitelist()
def penny_create_fund_account(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs,
            {
                "ifsc": "required",
                "account_holder_name": "required",
                "account_number": ["required", "decimal"],
            },
        )

        try:
            user = lms.__user()
        except UserNotFoundException:
            raise lms.exceptions.NotFoundException(_("User not found"))

        create_fund_acc = lms.call_penny_create_fund_account(
            user.name,
            data.get("ifsc"),
            data.get("account_number"),
            data.get("account_holder_name"),
        )

        if create_fund_acc.get("message") == "failed":
            raise lms.exceptions.RespondWithFailureException(_("failed"))

        elif create_fund_acc.get("message") == "Special Characters not allowed":
            raise lms.exceptions.RespondWithFailureException(
                _("Special Characters not allowed")
            )

        elif (
            create_fund_acc.get("message")
            == "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
        ):
            raise lms.exceptions.RespondWithFailureException(
                _("Penny Drop Fund Account Error - Razorpay Key Secret Missing")
            )
        else:
            return utils.respondWithSuccess(
                message=frappe._("success"), data=create_fund_acc
            )

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        frappe.log_error(
            title="Penny Drop Create fund account Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create fund account Error: "
            + str(e.args),
        )
        return e.respond()


@frappe.whitelist()
def penny_create_fund_account_validation(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs,
            {
                "fa_id": "required",
                "bank_account_type": "",
                "branch": "required",
                "city": "required",
                "personalized_cheque": "required",
            },
        )

        # check user
        try:
            user = lms.__user()
        except UserNotFoundException:
            raise lms.exceptions.NotFoundException(_("User not found"))

        # check Loan Customer
        customer = lms.__customer(user.name)
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        # user KYC
        try:
            user_kyc = lms.__user_kyc(user.name)
        except UserKYCNotFoundException:
            raise lms.exceptions.RespondWithFailureException(_("User KYC not found"))

        fund_acc_validation = lms.call_penny_create_fund_account_validation(
            user.name,
            data.get("fa_id"),
            data.get("bank_account_type"),
            data.get("branch"),
            data.get("city"),
            data.get("personalized_cheque"),
        )

        if (
            fund_acc_validation.get("message")
            == "Penny Drop Fund Account Validation Error - Razorpay Key Secret Missing"
        ):
            raise lms.exceptions.RespondWithFailureException(
                _(
                    "Penny Drop Fund Account Validation Error - Razorpay Key Secret Missing"
                )
            )

        elif (
            fund_acc_validation.get("message")
            == "Penny Drop Fund Account Validation Error - Razorpay Bank Account Missing"
        ):
            raise lms.exceptions.RespondWithFailureException(
                _(
                    "Penny Drop Fund Account Validation Error - Razorpay Bank Account Missing"
                )
            )

        elif fund_acc_validation.get("message") == "waiting for response from bank":
            raise lms.exceptions.RespondWithFailureException(
                _("waiting for response from bank")
            )

        elif (
            fund_acc_validation.get("message")
            == "We have found a mismatch in the account holder name as per the fetched data"
        ):
            data = {
                "fav_id": fund_acc_validation.get("data_resp").get("fav_id"),
                "status": fund_acc_validation.get("data_resp").get("status"),
            }
            return utils.respondWithSuccess(
                message=fund_acc_validation.get("message"), data=data
            )
        elif (
            fund_acc_validation.get("message")
            == "Your account details have not been successfully verified"
        ):
            data = {
                "fav_id": fund_acc_validation.get("data_resp").get("fav_id"),
                "status": fund_acc_validation.get("data_resp").get("status"),
            }
            return utils.respondWithSuccess(
                message=fund_acc_validation.get("message"), data=data
            )
        else:
            message = "Your account details have been successfully verified"
            data = {
                "fav_id": fund_acc_validation.get("id"),
                "status": fund_acc_validation.get("status"),
            }
            return utils.respondWithSuccess(message=message, data=data)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        frappe.log_error(
            title="Penny Drop Create fund account validation Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create fund account validation Error: "
            + str(e.args),
        )
        return e.respond()


@frappe.whitelist()
def penny_create_fund_account_validation_by_id(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs,
            {
                "fav_id": "required",
                "personalized_cheque": "required",
            },
        )
        validation_by_id = lms.call_penny_create_fund_account_validation_by_id(
            fav_id=data.get("fav_id"),
            personalized_cheque=data.get("personalized_cheque"),
        )
        if validation_by_id.get("message") == "failed":
            raise lms.exceptions.RespondWithFailureException(_("Failed"))

        elif validation_by_id.get("message") == "User not found":
            raise lms.exceptions.NotFoundException(_("User not found"))

        elif validation_by_id.get("message") == "Customer not found":
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        elif validation_by_id.get("message") == "User KYC not found":
            raise lms.exceptions.RespondWithFailureException(_("User KYC not found"))

        elif (
            validation_by_id.get("message")
            == "Penny Drop Fund Account Error - Razorpay Key Secret Missing"
        ):
            raise lms.exceptions.RespondWithFailureException(
                _("Penny Drop Fund Account Error - Razorpay Key Secret Missing")
            )

        elif validation_by_id.get("message") == "waiting for response from bank":
            raise lms.exceptions.respondWithSuccess(_("waiting for response from bank"))

        elif (
            validation_by_id.get("message")
            == "We have found a mismatch in the account holder name as per the fetched data"
        ):
            data = {
                "fav_id": validation_by_id.get("data_resp").get("fav_id"),
                "status": validation_by_id.get("data_resp").get("status"),
            }
            return utils.respondWithSuccess(
                message=validation_by_id.get("message"), data=data
            )
        elif (
            validation_by_id.get("message")
            == "Your account details have not been successfully verified"
        ):
            data = {
                "fav_id": validation_by_id.get("data_resp").get("fav_id"),
                "status": validation_by_id.get("data_resp").get("status"),
            }
            return utils.respondWithSuccess(
                message=validation_by_id.get("message"), data=data
            )
        else:
            message = "Your account details have been successfully verified"
            data = {
                "fav_id": validation_by_id.get("id"),
                "status": validation_by_id.get("status"),
            }
            return utils.respondWithSuccess(message=message, data=data)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        frappe.log_error(
            title="Penny Drop Create fund account validation Error",
            message=frappe.get_traceback()
            + "\n\nPenny Drop Create fund account validation Error: "
            + str(e.args),
        )
        return e.respond()


@frappe.whitelist()
def consent_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"consent_name": "required"})

        customer = lms.__customer()
        if not customer:
            raise lms.exceptions.NotFoundException(_("Customer not found"))

        consent_list = frappe.get_list("Consent", pluck="name", ignore_permissions=True)

        if data.get("consent_name") not in consent_list:
            raise lms.exceptions.NotFoundException(_("Consent not found"))
        try:
            consent_details = frappe.get_doc("Consent", data.get("consent_name"))
        except frappe.DoesNotExistError:
            raise lms.exceptions.NotFoundException(_("Consent not found"))
        return utils.respondWithSuccess(data=consent_details)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def ckyc_search(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs,
            {
                "pan_no": "required",
                "accept_terms": ["required", "between:0,1", "decimal"],
            },
        )

        ckyc_no = {}

        reg = lms.regex_special_characters(
            search=data.get("pan_no"),
            regex=re.compile("[A-Za-z]{5}[0-9]{4}[A-Za-z]{1}"),
        )
        if not reg or len(data.get("pan_no")) != 10:
            raise lms.exceptions.FailureException(_("Invalid PAN"))

        if not data.get("accept_terms"):
            raise lms.exceptions.UnauthorizedException(
                _("Please accept Terms and Conditions.")
            )

        customer = lms.__customer()
        if frappe.utils.get_url() == "https://spark.loans":
            return utils.respondWithFailure(
                status=417,
                message="Under Maintenance! Please try again after some time.",
            )

        res_json = lms.ckyc_dot_net(customer, data.get("pan_no"), is_for_search=True)

        if res_json.get("status") == 200 and not res_json.get("error"):
            pid_data = (
                json.loads(res_json.get("data"))
                .get("PID_DATA")
                .get("SearchResponsePID")
            )
            if type(pid_data) != list:
                pid_data = [pid_data]
            ckyc_no_ = ",".join(
                [
                    "".join(filter(str.isdigit, pid.get("CKYC_NO")))
                    + ":"
                    + pid.get("KYC_DATE")
                    for pid in pid_data
                    if not pid.get("CONSTITUTION_TYPE")
                ]
            )

            ckyc_no = {"ckyc_no": ckyc_no_}
            kyc_consent_doc = frappe.get_doc(
                {
                    "doctype": "User Consent",
                    "mobile": lms.__user().phone,
                    "consent": "Kyc",
                }
            )
            kyc_consent_doc.insert(ignore_permissions=True)
            frappe.db.commit()
        else:
            lms.log_api_error(mess=str(res_json))
            return utils.respondWithFailure(
                status=res_json.get("status"),
                message="Sorry! Our system has not been able to validate your KYC. Please try again after sometime.",
                data=res_json.get("error"),
            )

        return utils.respondWithSuccess(data=ckyc_no)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def ckyc_download(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs, {"pan_no": "required", "dob": "required", "ckyc_no": "required"}
        )

        reg = lms.regex_special_characters(
            search=data.get("pan_no"),
            regex=re.compile("[A-Za-z]{5}[0-9]{4}[A-Za-z]{1}"),
        )
        if not reg or len(data.get("pan_no")) != 10:
            raise lms.exceptions.FailureException(_("Invalid PAN"))

        pid_data = {}
        customer = lms.__customer()
        user_kyc_name = ""
        data["dob"] = datetime.strptime(data.get("dob"), "%d-%m-%Y").strftime(
            "%d-%m-%Y"
        )
        data["ckyc_no"] = data.get("ckyc_no").split(",")
        kyc_dict = {}

        for ckyc in data.get("ckyc_no"):
            res_json = lms.ckyc_dot_net(
                cust=customer,
                pan_no=data.get("pan_no"),
                is_for_download=True,
                dob=data.get("dob"),
                ckyc_no=ckyc.split(":")[0],
            )

            if res_json.get("status") == 200 and not res_json.get("error"):
                try:
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
                            "date_of_birth": datetime.strptime(
                                data.get("dob"), "%d-%m-%Y"
                            ),
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
                            "fatherspouse_flag": personal_details.get(
                                "FATHERSPOUSE_FLAG"
                            ),
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
                            "perm_corres_sameflag": personal_details.get(
                                "PERM_CORRES_SAMEFLAG"
                            ),
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
                                photos_ = lms.upload_image_to_doctype(
                                    customer=customer,
                                    seq_no=r.get("REL_TYPE"),
                                    image_=r.get("PHOTO_DATA"),
                                    img_format=r.get("PHOTO_TYPE"),
                                )
                                perm_poi_photos_ = lms.upload_image_to_doctype(
                                    customer=customer,
                                    seq_no=r.get("REL_TYPE"),
                                    image_=r.get("PERM_POI_DATA"),
                                    img_format=r.get("PERM_POI_IMAGE_TYPE"),
                                )
                                corres_poi_photos_ = lms.upload_image_to_doctype(
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
                                        "corres_add_country": r.get(
                                            "CORRES_ADD_COUNTRY"
                                        ),
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
                                        "perm_poi_image_type": r.get(
                                            "PERM_POI_IMAGE_TYPE"
                                        ),
                                        "perm_poi": perm_poi_photos_,
                                        "corres_poi_image_type": r.get(
                                            "CORRES_POI_IMAGE_TYPE"
                                        ),
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
                                        "e_kyc_authentication": r.get(
                                            "E_KYC_AUTHENTICATION"
                                        ),
                                    },
                                )

                    if image_details:
                        image_ = image_details.get("IMAGE")
                        if image_:
                            if type(image_) != list:
                                image_ = [image_]

                            for im in image_:
                                image_data = lms.upload_image_to_doctype(
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
                    user_kyc_name = user_kyc.name
                    kyc_dict.update(
                        {
                            user_kyc_name: datetime.strptime(
                                ckyc.split(":")[1], "%d-%m-%Y"
                            )
                        }
                    )
                    frappe.db.commit()

                except Exception:
                    raise lms.exceptions.RespondFailureException()
            else:
                frappe.db.rollback
                lms.log_api_error(mess=str(res_json))
                return utils.respondWithFailure(
                    status=res_json.get("status"),
                    message="Sorry! Our system has not been able to validate your KYC. Please try again after sometime.",
                    data=res_json.get("error"),
                )
        user_kyc_name = ",".join(
            dict(sorted(kyc_dict.items(), key=lambda item: item[1])).keys()
        )
        if len(user_kyc_name.split(",")) > 1:
            for dup_kyc in user_kyc_name.split(",")[1:]:
                frappe.get_doc(
                    {
                        "doctype": "Duplicate KYC",
                        "user_kyc": dup_kyc,
                        "user": lms.__user().name,
                        "parent": user_kyc_name.split(",")[0],
                        "parentfield": "duplicate_kyc",
                        "parenttype": "User KYC",
                    }
                ).insert(ignore_permissions=True)

            filter = "= '{}'".format(user_kyc_name.split(",")[1])
            if len(user_kyc_name.split(",")[1:]) > 1:
                filter = "in {}".format(
                    lms.convert_list_to_tuple_string(
                        [d.name for d in user_kyc_name.split(",")[1:]]
                    )
                )
            frappe.db.sql(
                "update `tabUser KYC` set parent_kyc='{main_kyc}' where name {filter}".format(
                    main_kyc=user_kyc_name.split(",")[0], filter=filter
                ),
                debug=True,
            )

            frappe.db.commit()
        return utils.respondWithSuccess(data={"user_kyc_name": user_kyc_name})
    except utils.exceptions.APIException as e:
        frappe.db.rollback
        lms.log_api_error()
        return e.respond()


def validate_address(address):
    if type(address) is not dict:
        raise lms.exceptions.FailureException(
            message=frappe._("address details should be dictionary.")
        )

    perm_add = address["permanent_address"]
    corres_add = address["corresponding_address"]

    add_details = [
        "address_line1",
        "address_line2",
        "address_line3",
        "city",
        "pin_code",
        "state",
        "district",
        "country",
        "poa_type",
        "address_proof_image",
    ]

    if not all(key in perm_add for key in add_details):
        raise lms.exceptions.FailureException(
            message=frappe._("Keys missing in Permanent address details")
        )

    if not all(key in corres_add for key in add_details):
        raise lms.exceptions.FailureException(
            message=frappe._("Keys missing in Corresponding address details")
        )

    if len(perm_add) == 0:
        raise lms.exceptions.FailureException(
            message=frappe._("Permanent Address Required")
        )

    address_valid = True
    if type(perm_add) is not dict:
        address_valid = False
        message = frappe._("Permanent Address should be dictionary")

    if address_valid:
        for i in perm_add.values():
            if type(i) is not str:
                address_valid = False
                message = frappe._("permanent address should be in string format")
                break

        for k, v in perm_add.items():
            if (
                k
                in [
                    "address_line1",
                    "city",
                    "pin_code",
                    "state",
                    "district",
                    "country",
                    "address_proof_image",
                    "poa_type",
                ]
                and not v
            ):
                raise lms.exceptions.FailureException(
                    message=frappe._(
                        "{} field required permanent address".format(
                            k.title().replace("_", " ")
                        )
                    )
                )

    if len(corres_add) == 0:
        raise lms.exceptions.FailureException(
            message=frappe._("Corresponding Address Required")
        )

    if type(corres_add) is not dict:
        address_valid = False
        message = frappe._("Corresponding Address should be dictionary")

    if address_valid:
        for i in corres_add.values():
            if type(i) is not str:
                address_valid = False
                message = frappe._("Corresponding should be in string format")
                break

        for k, v in corres_add.items():
            if (
                k
                in [
                    "address_line1",
                    "city",
                    "pin_code",
                    "state",
                    "district",
                    "country",
                    "address_proof_image",
                    "poa_type",
                ]
                and not v
            ):
                raise lms.exceptions.FailureException(
                    message=frappe._(
                        "{} field required in corresponding address".format(
                            k.title().replace("_", " ")
                        )
                    )
                )

    if not address_valid:
        raise lms.exceptions.FailureException(message=message)

    return address


@frappe.whitelist()
def ckyc_consent_details(**kwargs):
    try:
        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs,
            {
                "user_kyc_name": "required",
                "address_details": "",
                "accept_terms": "",
                "is_loan_renewal": "required",
            },
        )

        # user kyc name = first entry in kyc doctype
        # multiple kyc = remaining kyc entries
        # add multiple kyc names in parent kyc doctype
        # add parent kyc to all multiple kyc
        multiple_kyc = data.get("user_kyc_name").split(",")[1:]
        data["user_kyc_name"] = data.get("user_kyc_name").split(",")[0]

        if data.get("address_details") and not data.get("accept_terms"):
            raise lms.exceptions.UnauthorizedException(
                message=_("Please accept Terms and Conditions.")
            )

        if data.get("user_kyc_name") and data.get("is_loan_renewal") == 1:
            customer = lms.__customer()
            user_kyc_doc = frappe.get_doc("User KYC", customer.choice_kyc)

            res_json = lms.ckyc_dot_net(
                cust=customer,
                pan_no=user_kyc_doc.pan_no,
                is_for_download=True,
                dob=user_kyc_doc.dob,
                ckyc_no=user_kyc_doc.ckyc_no,
            )
            if res_json.get("status") == 200 and not res_json.get("error"):
                try:
                    new_user_kyc = lms.ckyc_commit(
                        res_json=res_json, customer=customer, dob=user_kyc_doc.dob
                    )
                    new_user_kyc_doc = frappe.get_doc("User KYC", new_user_kyc.name)
                    new_user_kyc_doc.updated_kyc = 1
                    banks = []
                    for i in user_kyc_doc.bank_account:
                        bank = frappe.get_doc(
                            {
                                "parent": new_user_kyc_doc.name,
                                "parenttype": "User KYC",
                                "parentfield": "bank_account",
                                "bank_status": i.get("bank_status"),
                                "bank": i.get("bank"),
                                "branch": i.get("branch"),
                                "account_number": i.get("account_number"),
                                "ifsc": i.get("ifsc"),
                                "city": i.get("city"),
                                "is_default": i.get("is_default"),
                                "penny_request_id": i.get("penny_request_id"),
                                "account_holder_name": i.get("account_holder_name"),
                                "personalized_cheque": i.get("personalized_cheque"),
                                "account_type": i.get("account_type"),
                                "bank_transaction_status": i.get(
                                    "bank_transaction_status"
                                ),
                                "notification_sent": i.get("notification_sent"),
                                "doctype": "User Bank Account",
                            }
                        ).insert(ignore_permissions=True)
                        banks.append(bank)
                    new_user_kyc_doc.bank_account = banks
                    new_user_kyc_doc.save(ignore_permissions=True)
                    frappe.db.commit()

                    ckyc_address_doc = frappe.get_doc(
                        {
                            "doctype": "Customer Address Details",
                            "perm_line1": new_user_kyc_doc.perm_line1,
                            "perm_line2": new_user_kyc_doc.perm_line2,
                            "perm_line3": new_user_kyc_doc.perm_line3,
                            "perm_city": new_user_kyc_doc.perm_city,
                            "perm_dist": new_user_kyc_doc.perm_dist,
                            "perm_state": new_user_kyc_doc.perm_state_name,
                            "perm_country": new_user_kyc_doc.perm_country_name,
                            "perm_pin": new_user_kyc_doc.perm_pin,
                            "perm_poa": "",
                            "perm_image": "",
                            "corres_poa_image": "",
                            "perm_corres_flag": new_user_kyc_doc.perm_corres_sameflag,
                            "corres_line1": new_user_kyc_doc.corres_line1,
                            "corres_line2": new_user_kyc_doc.corres_line2,
                            "corres_line3": new_user_kyc_doc.corres_line3,
                            "corres_city": new_user_kyc_doc.corres_city,
                            "corres_dist": new_user_kyc_doc.corres_dist,
                            "corres_state": new_user_kyc_doc.corres_state_name,
                            "corres_country": new_user_kyc_doc.corres_country_name,
                            "corres_pin": new_user_kyc_doc.corres_pin,
                            "corres_poa": "",
                        }
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()

                    try:
                        if new_user_kyc_doc.updated_kyc == 1:
                            consent_details = frappe.get_doc("Consent", "Re-Ckyc")
                        else:
                            consent_details = frappe.get_doc("Consent", "Ckyc")
                    except frappe.DoesNotExistError:
                        raise lms.exceptions.NotFoundException(
                            message=_("Consent not found")
                        )

                    poa_type = frappe.get_list(
                        "Proof of Address Master",
                        pluck="poa_name",
                        ignore_permissions=True,
                    )

                    country = frappe.get_all(
                        "Country Master",
                        fields=["country"],
                        pluck="country",
                        order_by="country asc",
                    )

                    user_kyc = lms.user_kyc_hashing(new_user_kyc_doc)
                    if user_kyc.address_details:
                        address = frappe.get_doc(
                            "Customer Address Details", user_kyc.address_details
                        )
                    else:
                        address = ""

                    data_res = {
                        "user_kyc_doc": user_kyc,
                        "consent_details": consent_details,
                        "poa_type": poa_type,
                        "country": country,
                        "address": address,
                    }
                    message = "Success"

                    return utils.respondWithSuccess(message=message, data=data_res)

                except Exception as e:
                    lms.log_api_error(mess=str(res_json))
                    return utils.respondWithFailure(
                        status=res_json.get("status"),
                        message="Something went wrong",
                        data=str(e),
                    )
            else:
                lms.log_api_error(mess=str(res_json))
                return utils.respondWithFailure(
                    status=res_json.get("status"),
                    message="Sorry! Our system has not been able to validate your KYC. Please try again after sometime.",
                    data=res_json.get("error"),
                )
        else:
            try:
                user_kyc = frappe.get_doc("User KYC", data.get("user_kyc_name"))
            except UserKYCNotFoundException:
                user_kyc = None
            try:
                if user_kyc.updated_kyc == 1:
                    consent_details = frappe.get_doc("Consent", "Re-Ckyc")
                else:
                    consent_details = frappe.get_doc("Consent", "Ckyc")
            except frappe.DoesNotExistError:
                raise lms.exceptions.NotFoundException(message=_("Consent not found"))

            if data.get("address_details") and not data.get("accept_terms"):
                raise lms.exceptions.UnauthorizedException(
                    message=_("Please accept Terms and Conditions.")
                )

            poa_type = frappe.get_list(
                "Proof of Address Master", pluck="poa_name", ignore_permissions=True
            )

            country = frappe.get_all(
                "Country Master",
                fields=["country"],
                pluck="country",
                order_by="country asc",
            )

            user_kyc = lms.user_kyc_hashing(user_kyc)
            if user_kyc.address_details:
                address = frappe.get_doc(
                    "Customer Address Details", user_kyc.address_details
                )

            else:
                address = ""

            data_res = {
                "user_kyc_doc": user_kyc,
                "consent_details": consent_details,
                "poa_type": poa_type,
                "country": country,
                "address": address,
            }
            message = "Success"

            if data.get("address_details") and data.get("accept_terms"):
                validate_address(
                    address=data.get("address_details", {}),
                )
                user_kyc_doc = frappe.get_doc("User KYC", user_kyc.name)
                address = []
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_line1,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("address_line1"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_line2,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("address_line2"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_line3,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("address_line3"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_city,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("city"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_dist,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("district"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_state_name,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("state"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_country_name,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("country"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.perm_pin,
                        "=",
                        data.get("address_details")
                        .get("permanent_address")
                        .get("pin_code"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_line1,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("address_line1"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_line2,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("address_line2"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_line3,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("address_line3"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_city,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("city"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_dist,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("district"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_state_name,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("state"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_country_name,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("country"),
                    )
                )
                address.append(
                    frappe.compare(
                        user_kyc_doc.corres_pin,
                        "=",
                        data.get("address_details")
                        .get("corresponding_address")
                        .get("pin_code"),
                    )
                )

                perm_add_photos = lms.upload_image_to_doctype(
                    customer=lms.__customer(user_kyc_doc.user),
                    seq_no="perm-add",
                    image_=data.get("address_details")
                    .get("permanent_address")
                    .get("address_proof_image"),
                    img_format="png",
                    img_folder="user_ckyc_address",
                    compress=1,
                )
                corres_add_photos = lms.upload_image_to_doctype(
                    customer=lms.__customer(user_kyc_doc.user),
                    seq_no="corres-add",
                    image_=data.get("address_details")
                    .get("corresponding_address")
                    .get("address_proof_image"),
                    img_format="png",
                    img_folder="user_ckyc_address",
                    compress=1,
                )

                ckyc_address_doc = frappe.get_doc(
                    {
                        "doctype": "Customer Address Details",
                        "perm_line1": data.get("address_details")
                        .get("permanent_address")
                        .get("address_line1"),
                        "perm_line2": data.get("address_details")
                        .get("permanent_address")
                        .get("address_line2"),
                        "perm_line3": data.get("address_details")
                        .get("permanent_address")
                        .get("address_line3"),
                        "perm_city": data.get("address_details")
                        .get("permanent_address")
                        .get("city"),
                        "perm_dist": data.get("address_details")
                        .get("permanent_address")
                        .get("district"),
                        "perm_state": data.get("address_details")
                        .get("permanent_address")
                        .get("state"),
                        "perm_country": data.get("address_details")
                        .get("permanent_address")
                        .get("country"),
                        "perm_pin": data.get("address_details")
                        .get("permanent_address")
                        .get("pin_code"),
                        "perm_poa": data.get("address_details")
                        .get("permanent_address")
                        .get("poa_type"),
                        "perm_image": perm_add_photos,
                        "corres_poa_image": corres_add_photos,
                        "perm_corres_flag": data.get("address_details").get(
                            "perm_corres_flag"
                        ),
                        "corres_line1": data.get("address_details")
                        .get("corresponding_address")
                        .get("address_line1"),
                        "corres_line2": data.get("address_details")
                        .get("corresponding_address")
                        .get("address_line2"),
                        "corres_line3": data.get("address_details")
                        .get("corresponding_address")
                        .get("address_line3"),
                        "corres_city": data.get("address_details")
                        .get("corresponding_address")
                        .get("city"),
                        "corres_dist": data.get("address_details")
                        .get("corresponding_address")
                        .get("district"),
                        "corres_state": data.get("address_details")
                        .get("corresponding_address")
                        .get("state"),
                        "corres_country": data.get("address_details")
                        .get("corresponding_address")
                        .get("country"),
                        "corres_pin": data.get("address_details")
                        .get("corresponding_address")
                        .get("pin_code"),
                        "corres_poa": data.get("address_details")
                        .get("corresponding_address")
                        .get("poa_type"),
                    }
                ).insert(ignore_permissions=True)
                user_kyc_doc.address_details = ckyc_address_doc.name
                user_kyc_doc.consent_given = 1
                if False in address:
                    user_kyc_doc.is_edited = 1
                    ckyc_address_doc.is_edited = 1
                    ckyc_address_doc.save(ignore_permissions=True)
                if multiple_kyc:
                    for kyc in multiple_kyc:
                        kyc_doc = frappe.get_doc("User KYC", kyc)
                        kyc_doc.consent_given = 1
                        kyc_doc.address_details = ckyc_address_doc.name
                        if False in address:
                            kyc_doc.is_edited = 1
                        kyc_doc.save(ignore_permissions=True)
                user_kyc_doc.save(ignore_permissions=True)
                frappe.db.commit()
                if user_kyc_doc.updated_kyc == 0:
                    kyc_consent_doc = frappe.get_doc(
                        {
                            "doctype": "User Consent",
                            "mobile": lms.__user().phone,
                            "consent": "Ckyc",
                        }
                    )
                else:
                    kyc_consent_doc = frappe.get_doc(
                        {
                            "doctype": "User Consent",
                            "mobile": lms.__user().phone,
                            "consent": "Re-Ckyc",
                        }
                    )
                kyc_consent_doc.insert(ignore_permissions=True)

                frappe.db.commit()
                message = "Your KYC verification is in process, it will be executed in next 24 hours"

            # response all these for user kyc get request
            return utils.respondWithSuccess(message=message, data=data_res)
    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def get_bank_details():
    try:
        utils.validator.validate_http_method("POST")
        las_settings = frappe.get_single("LAS Settings")
        try:
            user_kyc = lms.__user_kyc()
        except UserKYCNotFoundException:
            user_kyc = None
        if user_kyc:
            params = {
                "PANNum": user_kyc.pan_no,
                "dob": user_kyc.date_of_birth,
            }
            headers = {
                "businessUnit": las_settings.choice_business_unit,
                "userId": las_settings.choice_user_id,
                "investorId": las_settings.choice_investor_id,
                "ticket": las_settings.choice_ticket,
            }

            res = requests.get(
                las_settings.choice_pan_api, params=params, headers=headers
            )
            if res.status_code != 200:
                lms.log_api_error()
                raise FailureException()
            data = res.json()
            log = {
                "url": las_settings.choice_pan_api,
                "headers": headers,
                "request": str(params),
                "response": data,
            }
            lms.create_log(log, "get_bank_details_log")
            if res.ok and "errorCode" not in data and data.get("banks"):
                user_kyc.kyc_type = "CHOICE"
                user_kyc.email = data["emailId"]
                user_kyc.choice_mob_no = data["mobileNum"]
                user_kyc.bank_account = []
                user_kyc.save(ignore_permissions=True)
                frappe.db.commit()
                user_kyc_doc = frappe.get_doc("User KYC", user_kyc.name)

                for bank in data["banks"]:
                    user_kyc_doc.append(
                        "bank_account",
                        {
                            "bank": bank["bank"],
                            "bank_address": bank["bankAddress"],
                            "branch": bank["branch"],
                            "contact": bank["contact"],
                            "account_type": bank["accountType"],
                            "account_number": bank["accountNumber"],
                            "ifsc": bank["ifsc"],
                            "micr": bank["micr"],
                            "bank_mode": bank["bankMode"],
                            "bank_code": bank["bankcode"],
                            "bank_zip_code": bank["bankZipCode"],
                            "city": bank["city"],
                            "district": bank["district"],
                            "state": bank["state"],
                            "is_default": bank["defaultBank"] == "Y",
                            "bank_status": "",
                        },
                    )
                user_kyc_doc = lms.user_kyc_hashing(user_kyc_doc)
                return utils.respondWithSuccess(data=user_kyc_doc)
            else:
                message = "Record does not exist."
                return utils.respondWithSuccess(message=message)

    except utils.exceptions.APIException as e:
        frappe.db.rollback()
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def pincode(**kwargs):
    try:
        utils.validator.validate_http_method("GET")
        data = utils.validator.validate(
            kwargs,
            {
                "pincode": "required",
            },
        )

        try:
            pincode = frappe.get_doc("Pincode Master", data.get("pincode"))
        except DoesNotExistError:
            raise lms.exceptions.NotFoundException(_("Pincode not found"))

        data_res = {"district": pincode.new_district, "state": pincode.state_name}

        return utils.respondWithSuccess(data=data_res)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def get_app_version_details():
    try:
        utils.validator.validate_http_method("GET")

        version_details = frappe.get_all(
            "Spark App Version",
            filters={"is_live": 1},
            fields=["*"],
            page_length=1,
        )
        if not version_details:
            return utils.respondNotFound(message=_("No Record found"))
        return utils.respondWithSuccess(data=version_details[0])
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def get_demat_details():
    try:
        utils.validator.validate_http_method("GET")
        user = lms.__user()
        log = {"start_time": str(frappe.utils.now_datetime()), "user": user.name}
        lms.create_log(log, "get_demat_details_api_start_time")
        user_kyc = frappe.get_all(
            "User KYC",
            filters={"user": user.name, "kyc_status": ("!=", "Rejected")},
            fields=["*"],
        )
        customer = lms.__customer(user.name)

        # get demat details from choice
        las_settings = frappe.get_single("LAS Settings")
        if user_kyc:
            payload = {
                "UserID": las_settings.choice_user_id,
                "ClientID": user_kyc[0].pan_no,
            }

            try:
                log_1 = {
                    "start_time": str(frappe.utils.now_datetime()),
                    "user": user.name,
                }
                res = requests.post(
                    las_settings.choice_securities_list_api,
                    json=payload,
                    headers={
                        "Accept": "application/json",
                        "Authorization": "jKW/RR7JMhigIpZbvEGiag==",
                    },
                )
                log_1["end_time"]: str(frappe.utils.now_datetime())
                lms.create_log(log_1, "get_demat_details_request_time")
                if not res.ok:
                    raise utils.exceptions.APIException(res.text)

                res_json = res.json()
                if res_json["Status"] != "Success":
                    frappe.delete_doc(
                        "Spark Demat Account",
                        frappe.get_all(
                            "Spark Demat Account",
                            {"customer": customer.name, "is_choice": 1},
                            pluck="name",
                        ),
                        ignore_permissions=True,
                    )

                if res_json.get("Response"):
                    distinct_demats = list(
                        {
                            frozenset(item.items()): item
                            for item in [
                                {
                                    "depository": i.get("Depository"),
                                    "stock_at": i.get("Stock_At"),
                                }
                                for i in res_json["Response"]
                            ]
                        }.values()
                    )

                    frappe.delete_doc(
                        "Spark Demat Account",
                        frappe.get_all(
                            "Spark Demat Account",
                            {"customer": customer.name, "is_choice": 1},
                            pluck="name",
                        ),
                        ignore_permissions=True,
                    )

                    for demat in distinct_demats:
                        frappe.get_doc(
                            {
                                "doctype": "Spark Demat Account",
                                "customer": customer.name,
                                "depository": demat["depository"],
                                "dpid": demat["stock_at"][:8],
                                "client_id": demat["stock_at"][8:],
                                "is_choice": 1,
                            }
                        ).insert(ignore_permissions=True)
                        frappe.db.commit()

            except requests.RequestException as e:
                raise utils.exceptions.APIException(str(e))

        demat_details = frappe.get_all(
            "Spark Demat Account",
            filters={"customer": customer.name},
            fields=["customer", "depository", "dpid", "client_id", "is_choice"],
        )
        if demat_details:
            for d in demat_details:
                d["stock_at"] = d.get("dpid") + d.get("client_id")
        log["end_time"] = str(frappe.utils.now_datetime())
        lms.create_log(log, "get_demat_details_time_log")
        return utils.respondWithSuccess(data=demat_details)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def shares_eligibility(**kwargs):
    try:
        utils.validator.validate_http_method("GET")
        user = lms.__user()
        log_1 = {"start_time": str(frappe.utils.now_datetime()), "user": user.name}
        lms.create_log(log_1, "shares_eligibility_api_start_time")

        data = utils.validator.validate(
            kwargs,
            {"lender": "", "level": "", "demat": ""},
        )
        reg = lms.regex_special_characters(
            search=data.get("lender")
            if data.get("lender")
            else "" + data.get("level")
            if data.get("level")
            else ""
        )
        if reg:
            raise lms.exceptions.FailureException(_(special_char_not_allowed))

        if not data.get("lender", None):
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Atleast one lender required"),
            )
        else:
            lender_list = data.get("lender").split(",")

        if not data.get("level"):
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Atleast one level required"),
            )

        if isinstance(data.get("level"), str):
            data["level"] = data.get("level").split(",")

        customer = lms.__customer()
        user_kyc = lms.__user_kyc()
        levels = lms.convert_list_to_tuple_string(data.get("level"))
        if data.get("demat"):
            demat_acc_no = data.get("demat")
            dpid = data.get("demat")[:8]
            client_id = data.get("demat")[8:]
            spark_demat_acc = frappe.get_all(
                "Spark Demat Account",
                filters={
                    "customer": customer.name,
                    "dpid": dpid,
                    "client_id": client_id,
                },
                fields=["customer", "depository", "dpid", "client_id", "is_choice"],
            )
            if not spark_demat_acc:
                raise lms.exceptions.NotFoundException(_("Demat account not found"))

            securities_list = []
            is_choice = spark_demat_acc[0].is_choice
            if spark_demat_acc[0].is_choice == 1:
                las_settings = frappe.get_single("LAS Settings")
                # get securities list from choice
                payload = {
                    "UserID": las_settings.choice_user_id,
                    "ClientID": user_kyc.pan_no,
                }

                try:
                    res = requests.post(
                        las_settings.choice_securities_list_api,
                        json=payload,
                        headers={
                            "Accept": "application/json",
                            "Authorization": "jKW/RR7JMhigIpZbvEGiag==",
                        },
                    )
                    if not res.ok:
                        raise utils.exceptions.APIException(res.text)

                    res_json = res.json()
                    log = {
                        "url": las_settings.choice_securities_list_api,
                        "headers": {
                            "Accept": "application/json",
                            "Authorization": "jKW/RR7JMhigIpZbvEGiag==",
                        },
                        "request": payload,
                        "response": res_json,
                    }
                    lms.create_log(log, "securities_log")
                    frappe.logger().info(res_json)
                    if res_json["Status"] != "Success":
                        raise lms.exceptions.NotFoundException()

                    # setting eligibility
                    securities_list = [
                        i
                        for i in res_json["Response"]
                        if i.get("Price") > 0 and i.get("Quantity") > 0
                    ]
                    security_stock_at_list = [i["Stock_At"] for i in securities_list]

                    if res_json["Response"]:
                        # bulk insert fields
                        fields = [
                            "name",
                            "pan",
                            "isin",
                            "branch",
                            "client_code",
                            "client_name",
                            "scrip_name",
                            "depository",
                            "stock_at",
                            "quantity",
                            "price",
                            "scrip_value",
                            "holding_as_on",
                            "creation",
                            "modified",
                            "owner",
                            "modified_by",
                        ]

                        values = []
                        for i in securities_list:
                            if i.get("Holding_As_On", None):
                                Holding_As_On = datetime.strptime(
                                    i["Holding_As_On"], "%Y-%m-%dT%H:%M:%S"
                                )
                            else:
                                Holding_As_On = frappe.utils.now_datetime()

                            values.append(
                                [
                                    i["Stock_At"] + "-" + i["ISIN"],
                                    user_kyc.pan_no,
                                    i["ISIN"],
                                    i["Branch"] if i.get("Branch", None) else "",
                                    i["Client_Code"]
                                    if i.get("Client_Code", None)
                                    else "",
                                    i["Client_Name"]
                                    if i.get("Client_Name", None)
                                    else "",
                                    i["Scrip_Name"],
                                    i["Depository"]
                                    if i.get("Depository", None)
                                    else "",
                                    i["Stock_At"],
                                    i["Quantity"],
                                    i["Price"],
                                    i["Scrip_Value"]
                                    if i.get("Scrip_Value", None)
                                    else "",
                                    Holding_As_On,
                                    frappe.utils.now(),
                                    frappe.utils.now(),
                                    frappe.session.user,
                                    frappe.session.user,
                                ]
                            )

                        # delete existng records
                        frappe.db.delete("Client Holding", {"pan": user_kyc.pan_no})

                        # bulk insert
                        frappe.db.bulk_insert(
                            "Client Holding",
                            fields=fields,
                            values=values,
                            ignore_duplicates=True,
                        )

                except requests.RequestException as e:
                    raise utils.exceptions.APIException(str(e))

                if res_json["Response"] and securities_list:
                    securities_list_ = [i["ISIN"] for i in securities_list]
                    instrument_type = "Shares"
                    securities_category_map = lms.get_allowed_securities(
                        securities_list_, lender_list, instrument_type, levels
                    )
                    securities_category_map_list = []
                    for i in securities_category_map:
                        securities_category_map_list.append(i)
                    final_securities_list = []
                    if securities_category_map_list:
                        pledge_waiting_securitites = frappe.db.sql(
                            """
                            SELECT GROUP_CONCAT(la.name) as loan_application, la.pledgor_boid,
                            lai.isin, sum(lai.pledged_quantity) as pledged_quantity,
                            ch.name
                            FROM `tabLoan Application` as la
                            LEFT JOIN `tabLoan Application Item` lai ON lai.parent = la.name
                            LEFT JOIN `tabClient Holding` ch ON ch.isin = lai.isin and ch.stock_at = la.pledgor_boid
                            where la.status='Waiting to be pledged'
                            AND ch.pan = '{}'
                            AND lai.isin in {}
                            AND la.customer = '{}'
                            group by ch.stock_at, lai.isin
                            order by la.pledgor_boid, lai.isin
                        """.format(
                                user_kyc.pan_no,
                                lms.convert_list_to_tuple_string(
                                    securities_category_map_list
                                ),
                                customer.name,
                            ),
                            as_dict=True,
                        )
                        if len(pledge_waiting_securitites) > 0:
                            for i in pledge_waiting_securitites:
                                try:
                                    if not securities_category_map[i["isin"]].get(
                                        "waiting_to_be_pledged_qty", None
                                    ):
                                        securities_category_map[i["isin"]][
                                            "waiting_to_be_pledged_qty"
                                        ] = {}

                                    securities_category_map[i["isin"]][
                                        "waiting_to_be_pledged_qty"
                                    ][i["pledgor_boid"]] = i["pledged_quantity"]
                                except KeyError:
                                    continue

                        waiting_for_lender_approval_securities = frappe.db.sql(
                            """
                            SELECT GROUP_CONCAT(cl.application_name) as loan_application, GROUP_CONCAT(cl.loan) as loan,
                            cl.pledgor_boid, cl.isin, sum(cl.quantity) as pledged_quantity,
                            ch.name
                            FROM `tabCollateral Ledger` as cl
                            LEFT JOIN `tabClient Holding` ch ON ch.isin = cl.isin and ch.stock_at = cl.pledgor_boid
                            WHERE (cl.lender_approval_status='' OR cl.lender_approval_status='Approved')
                            AND cl.request_type = 'Pledge'
                            AND DATE_FORMAT(cl.creation, '%Y-%m-%d') = '{}'
                            AND ch.pan = '{}'
                            AND cl.isin in {}
                            AND cl.customer = '{}'
                            group by ch.stock_at, cl.isin
                            order by cl.pledgor_boid, cl.isin;
                        """.format(
                                datetime.strftime(
                                    frappe.utils.now_datetime(), "%Y-%m-%d"
                                ),
                                user_kyc.pan_no,
                                lms.convert_list_to_tuple_string(
                                    securities_category_map_list
                                ),
                                customer.name,
                            ),
                            as_dict=True,
                        )
                        if len(waiting_for_lender_approval_securities) > 0:
                            for i in waiting_for_lender_approval_securities:
                                try:
                                    if not securities_category_map[i["isin"]].get(
                                        "waiting_for_approval_pledged_qty", None
                                    ):
                                        securities_category_map[i["isin"]][
                                            "waiting_for_approval_pledged_qty"
                                        ] = {}

                                    securities_category_map[i["isin"]][
                                        "waiting_for_approval_pledged_qty"
                                    ][i["pledgor_boid"]] = i["pledged_quantity"]
                                except KeyError:
                                    continue

                        unpledge_approved_securities = frappe.db.sql(
                            """
                            SELECT GROUP_CONCAT(cl.loan) as loan,
                            cl.pledgor_boid, cl.isin, sum(cl.quantity) as unpledged_quantity,
                            ch.name
                            FROM `tabCollateral Ledger` as cl
                            LEFT JOIN `tabClient Holding` ch ON ch.isin = cl.isin and ch.stock_at = cl.pledgor_boid
                            WHERE cl.lender_approval_status='Approved'
                            AND cl.request_type = 'Unpledge'
                            AND DATE_FORMAT(cl.creation, '%Y-%m-%d') = '{}'
                            AND ch.pan = '{}'
                            AND cl.isin in {}
                            AND cl.customer = '{}'
                            group by ch.stock_at, cl.isin
                            order by cl.pledgor_boid, cl.isin;
                        """.format(
                                datetime.strftime(
                                    frappe.utils.now_datetime(), "%Y-%m-%d"
                                ),
                                user_kyc.pan_no,
                                lms.convert_list_to_tuple_string(
                                    securities_category_map_list
                                ),
                                customer.name,
                            ),
                            as_dict=True,
                        )
                        if len(unpledge_approved_securities) > 0:
                            for i in unpledge_approved_securities:
                                try:
                                    if not securities_category_map[i["isin"]].get(
                                        "unpledged_quantity", None
                                    ):
                                        securities_category_map[i["isin"]][
                                            "unpledged_quantity"
                                        ] = {}

                                    securities_category_map[i["isin"]][
                                        "unpledged_quantity"
                                    ][i["pledgor_boid"]] = i["unpledged_quantity"]
                                except KeyError:
                                    continue

                        for i in securities_list:
                            # process actual qty
                            if i.get("Holding_As_On", None) and not isinstance(
                                i["Holding_As_On"], str
                            ):
                                i["Holding_As_On"] = i["Holding_As_On"].strftime(
                                    "%Y-%m-%dT%H:%M:%S"
                                )

                            try:
                                i["Category"] = securities_category_map[i["ISIN"]].get(
                                    "security_category"
                                )

                                i["Is_Eligible"] = True
                                i["Total_Qty"] = i["Quantity"]

                                if not i.get("waiting_to_be_pledged_qty", None):
                                    i["waiting_to_be_pledged_qty"] = 0

                                if securities_category_map[i["ISIN"]].get(
                                    "waiting_to_be_pledged_qty", None
                                ):
                                    if (
                                        i["Stock_At"]
                                        in securities_category_map[i["ISIN"]][
                                            "waiting_to_be_pledged_qty"
                                        ].keys()
                                    ):
                                        i["waiting_to_be_pledged_qty"] += float(
                                            securities_category_map[i["ISIN"]][
                                                "waiting_to_be_pledged_qty"
                                            ][i["Stock_At"]]
                                        )

                                if not i.get("waiting_for_approval_pledged_qty", None):
                                    i["waiting_for_approval_pledged_qty"] = 0

                                if securities_category_map[i["ISIN"]].get(
                                    "waiting_for_approval_pledged_qty", None
                                ):
                                    if (
                                        i["Stock_At"]
                                        in securities_category_map[i["ISIN"]][
                                            "waiting_for_approval_pledged_qty"
                                        ].keys()
                                    ):
                                        i["waiting_for_approval_pledged_qty"] += float(
                                            securities_category_map[i["ISIN"]][
                                                "waiting_for_approval_pledged_qty"
                                            ][i["Stock_At"]]
                                        )

                                if not i.get("unpledged_quantity", None):
                                    i["unpledged_quantity"] = 0

                                if securities_category_map[i["ISIN"]].get(
                                    "unpledged_quantity", None
                                ):
                                    if (
                                        i["Stock_At"]
                                        in securities_category_map[i["ISIN"]][
                                            "unpledged_quantity"
                                        ].keys()
                                    ):
                                        i["unpledged_quantity"] += float(
                                            securities_category_map[i["ISIN"]][
                                                "unpledged_quantity"
                                            ][i["Stock_At"]]
                                        )

                                available_quantity = (
                                    i["Quantity"] + i["unpledged_quantity"]
                                ) - (
                                    i["waiting_to_be_pledged_qty"]
                                    + i["waiting_for_approval_pledged_qty"]
                                )
                                i["Quantity"] = (
                                    available_quantity
                                    if available_quantity > 0
                                    else float(0)
                                )

                            except KeyError:
                                i["Is_Eligible"] = False
                                i["Category"] = None

                            i.update(is_choice=is_choice)
                            if i["Category"] != None and i["Stock_At"] == data.get(
                                "demat"
                            ):
                                final_securities_list.append(i)
                                image = frappe.get_all(
                                    "Allowed Security",
                                    filters={"isin": i["ISIN"]},
                                    fields=["amc_image", "eligible_percentage"],
                                )
                                if image[0].amc_image:
                                    image[0].amc_image = frappe.utils.get_url(
                                        image[0].amc_image
                                    )
                                i.update(
                                    amc_image=image[0].amc_image,
                                    eligible_percentage=image[0].eligible_percentage,
                                )

                    lender = lms.convert_list_to_tuple_string(lender_list)
                    lender_info = frappe.db.sql(
                        """select name, minimum_sanctioned_limit, maximum_sanctioned_limit, rate_of_interest from `tabLender` where name in {} """.format(
                            lender
                        ),
                        as_dict=True,
                    )
                    data = {
                        "Securities": final_securities_list,
                        "lender_info": lender_info,
                    }
                    if (
                        not data.get("Securities")
                        and demat_acc_no not in security_stock_at_list
                    ):
                        raise lms.exceptions.NotFoundException()
                    log_3 = {
                        "start_time": str(frappe.utils.now_datetime()),
                        "user": user.name,
                    }
                    lms.create_log(log_3, "shares_eligibility_end_time")
                    if res_json["Response"] and not data.get("Securities"):
                        return utils.respondWithSuccess(data=data)
                    return utils.respondWithSuccess(data=data)
                else:
                    raise lms.exceptions.NotFoundException()
            else:
                get_distinct_securities(lender_list, levels)
        else:
            get_distinct_securities(lender_list, levels)

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


def get_distinct_securities(lender_list, levels):
    try:
        lender = lms.convert_list_to_tuple_string(lender_list)
        lender_query = " and als.lender in {}".format(lender)
        sub_query = " and als.security_category in (select security_category from `tabConcentration Rule` where parent in {} and idx in {})".format(
            lender, levels
        )
        securities_list = frappe.db.sql(
            """select als.isin as ISIN, sc.category_name as Category, als.eligible_percentage, als.security_name as Scrip_Name, round(s.price,4) as Price, group_concat(als.lender,'') as lenders, 
                als.amc_image
                from `tabAllowed Security` als 
                LEFT JOIN `tabSecurity` s on s.isin = als.isin
                LEFT JOIN `tabSecurity Category` sc ON als.security_category = sc.name 
                where als.instrument_type='Shares' and
                s.price > 0{}{}
                group by als.isin
                order by als.creation desc;""".format(
                lender_query, sub_query
            ),
            as_dict=True,
        )
        lender_info = frappe.db.sql(
            """select name, minimum_sanctioned_limit, maximum_sanctioned_limit, rate_of_interest from `tabLender` where name in {} """.format(
                lender
            ),
            as_dict=True,
        )
        dummy_keys = {
            "Branch": None,
            "Client_Code": None,
            "Client_Name": None,
            "Depository": None,
            "Stock_At": None,
            "Quantity": None,
            "Scrip_Value": None,
            "Holding_As_On": None,
            "Is_Eligible": None,
            "Total_Qty": None,
            "waiting_to_be_pledged_qty": None,
            "waiting_for_approval_pledged_qty": None,
            "unpledged_quantity": None,
            "is_choice": 0,
        }
        for i in securities_list:
            i.update(dummy_keys)

        for scheme in securities_list:
            if scheme.amc_image:
                scheme.amc_image = frappe.utils.get_url(scheme.amc_image)

        data = {"Securities": securities_list, "lender_info": lender_info}
        log = {"start_time": str(frappe.utils.now_datetime())}
        lms.create_log(log, "shares_eligibility_end_time")
        if not securities_list and not data.get("Securities"):
            return utils.respondWithSuccess(data=data)
        return utils.respondWithSuccess(data=data)
    except Exception as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def au_penny_drop(**kwargs):
    try:

        utils.validator.validate_http_method("POST")
        data = utils.validator.validate(
            kwargs,
            {
                "ifsc": "required",
                "account_holder_name": "required",
                "account_number": "required",
                "bank_account_type": "",
                "bank": "required",
                "branch": "required",
                "city": "required",
                "personalized_cheque": "required",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("account_holder_name")
            + data.get("ifsc")
            + data.get("account_number")
            + data.get("bank_account_type")
            if data.get("bank_account_type")
            else "" + data.get("bank")
        )
        if reg:
            raise lms.exceptions.FailureException(_(special_char_not_allowed))

        # check user
        try:
            user = lms.__user()
        except UserNotFoundException:
            raise lms.exceptions.NotFoundException(_("User not found"))

        try:
            customer = lms.__customer(user.name)
        except CustomerNotFoundException:
            raise lms.exceptions.RespondWithFailureException(_("Customer not found"))

        try:
            user_kyc = lms.__user_kyc(user.name)
        except UserKYCNotFoundException:
            raise lms.exceptions.RespondWithFailureException(_("User KYC not found"))

        las_settings = frappe.get_single("LAS Settings")
        res_json = {}
        photos_ = lms.upload_image_to_doctype(
            customer=customer,
            seq_no=data.get("account_number"),
            image_=data.get("personalized_cheque"),
            img_format="png",
            img_folder="personalized_cheque",
            compress=1,
        )
        bank_acc = frappe.get_all(
            "User Bank Account",
            {
                "account_number": data.get("account_number"),
                "is_repeated": 0,
            },
            "*",
            order_by="creation desc",
        )
        mismatch_bank_acc = frappe.db.count(
            "User Bank Account",
            {"account_number": data.get("account_number"), "is_mismatched": 1},
        )
        penny_name_mismatch = frappe.get_all(
            "Penny Name Mismatch", {"account_number": data.get("account_number")}, "*"
        )
        if not mismatch_bank_acc and penny_name_mismatch:
            bank_account_list_ = frappe.get_all(
                "User Bank Account",
                filters={"parent": user_kyc.name},
                fields="*",
            )
            for b in bank_account_list_:
                other_bank_ = frappe.get_doc("User Bank Account", b.name)
                if other_bank_.is_default == 1:
                    other_bank_.is_default = 0
                    other_bank_.save(ignore_permissions=True)
                    frappe.db.commit()
            frappe.get_doc(
                {
                    "doctype": "User Bank Account",
                    "parentfield": "bank_account",
                    "parenttype": "User KYC",
                    "bank": data.get("bank"),
                    "branch": data.get("branch"),
                    "account_type": data.get("bank_account_type"),
                    "account_number": data.get("account_number"),
                    "ifsc": data.get("ifsc"),
                    "account_holder_name": data.get("account_holder_name"),
                    "personalized_cheque": photos_,
                    "city": data.get("city"),
                    "parent": user_kyc.name,
                    "is_default": True,
                    "bank_status": "Pending",
                    "penny_request_id": penny_name_mismatch[0].penny_request_id,
                    "bank_transaction_status": penny_name_mismatch[
                        0
                    ].bank_transaction_status,
                    "is_mismatched": 1,
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()
            return utils.respondWithSuccess(
                status=201,
                message="Your bank details are under the verification process",
            )

        if bank_acc and not penny_name_mismatch:
            if bank_acc[0].ifsc == data.get("ifsc"):
                if frappe.utils.now_datetime().date() >= (
                    bank_acc[0].creation.date()
                    + timedelta(days=las_settings.pennydrop_days_passed)
                ):
                    res_json = lms.au_pennydrop_api(data, user_kyc.fullname)
                else:
                    bank_account_list_ = frappe.get_all(
                        "User Bank Account",
                        filters={"parent": user_kyc.name},
                        fields="*",
                    )
                    for b in bank_account_list_:
                        other_bank_ = frappe.get_doc("User Bank Account", b.name)
                        if other_bank_.is_default == 1:
                            other_bank_.is_default = 0
                            other_bank_.save(ignore_permissions=True)
                            frappe.db.commit()
                    frappe.get_doc(
                        {
                            "doctype": "User Bank Account",
                            "parentfield": "bank_account",
                            "parenttype": "User KYC",
                            "bank": data.get("bank"),
                            "branch": data.get("branch"),
                            "account_type": data.get("bank_account_type"),
                            "account_number": data.get("account_number"),
                            "ifsc": data.get("ifsc"),
                            "account_holder_name": data.get("account_holder_name"),
                            "personalized_cheque": photos_,
                            "city": data.get("city"),
                            "parent": user_kyc.name,
                            "is_default": True,
                            "bank_status": "Pending",
                            "penny_request_id": bank_acc[0].penny_request_id,
                            "bank_transaction_status": bank_acc[
                                0
                            ].bank_transaction_status,
                            "is_repeated": 1,
                        }
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
                    return utils.respondWithSuccess(
                        message="Your account details have been successfully verified"
                    )
            else:
                res_json = lms.au_pennydrop_api(data, user_kyc.fullname)
        else:
            res_json = lms.au_pennydrop_api(data, user_kyc.fullname)

        if res_json:
            if (
                res_json.get("status_code") == 200
                and res_json.get("message") == "Success"
            ):
                result_ = res_json.get("body").get("Result")
                if res_json.get("body").get("status-code") == "101":
                    if result_.get("bankTxnStatus") == True:
                        if not result_.get("accountName"):
                            raise lms.exceptions.RespondFailureException(
                                _(
                                    "We have found a mismatch in the account holder name as per the fetched data"
                                )
                            )
                        else:
                            matching = res_json.get("body").get("fuzzy_match_score")
                            if (
                                not matching
                                or matching
                                < las_settings.penny_name_mismatch_percentage
                            ):
                                frappe.get_doc(
                                    {
                                        "doctype": "Penny Name Mismatch",
                                        "customer": customer.name,
                                        "user_kyc": user_kyc.name,
                                        "kyc_first_name": user_kyc.fname,
                                        "kyc_middle_name": user_kyc.mname,
                                        "kyc_last_name": user_kyc.lname,
                                        "kyc_full_name": user_kyc.fullname,
                                        "penny_response_account_name": result_.get(
                                            "accountName"
                                        ),
                                        "bank": data.get("bank"),
                                        "branch": data.get("branch"),
                                        "city": data.get("city"),
                                        "penny_request_id": res_json.get("body").get(
                                            "request_id"
                                        ),
                                        "ifsc": data.get("ifsc"),
                                        "account_number": result_.get("accountNumber"),
                                        "bank_transaction_status": result_.get(
                                            "bankTxnStatus"
                                        ),
                                        "personalized_cheque": photos_,
                                        "account_type": data.get("bank_account_type"),
                                        "penny_name_mismatch_percentage": matching,
                                    }
                                ).insert()
                                frappe.db.commit()
                                frappe.local.form_dict[
                                    "kyc_full_name"
                                ] = user_kyc.fullname
                                frappe.local.form_dict[
                                    "penny_response_account_name"
                                ] = result_.get("accountName")
                                raise lms.exceptions.RespondFailureException(
                                    _(
                                        "We have found a mismatch in the account holder name as per the fetched data"
                                    )
                                )
                            if user_kyc.kyc_type == "CHOICE":
                                bank_entry_name = frappe.db.get_value(
                                    "User Bank Account",
                                    {
                                        "parentfield": "bank_account",
                                        "parent": user_kyc.name,
                                        "account_number": result_.get("accountNumber"),
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
                                            other_bank = frappe.get_doc(
                                                "User Bank Account", b.name
                                            )
                                            if other_bank.is_default == 1:
                                                other_bank.is_default = 0
                                                other_bank.save(ignore_permissions=True)
                                    frappe.get_doc(
                                        {
                                            "doctype": "User Bank Account",
                                            "parentfield": "bank_account",
                                            "parenttype": "User KYC",
                                            "bank": data.get("bank"),
                                            "branch": data.get("branch"),
                                            "account_type": data.get(
                                                "bank_account_type"
                                            ),
                                            "account_number": result_.get(
                                                "accountNumber"
                                            ),
                                            "ifsc": data.get("ifsc"),
                                            "account_holder_name": data.get(
                                                "account_holder_name"
                                            ),
                                            "personalized_cheque": photos_,
                                            "city": data.get("city"),
                                            "parent": user_kyc.name,
                                            "is_default": True,
                                            "bank_status": "Pending",
                                            "penny_request_id": res_json.get(
                                                "body"
                                            ).get("request_id"),
                                            "bank_transaction_status": result_.get(
                                                "bankTxnStatus"
                                            ),
                                        }
                                    ).insert(ignore_permissions=True)
                                    frappe.db.commit()
                                else:
                                    # For existing choice bank entries
                                    bank_account_list = frappe.get_all(
                                        "User Bank Account",
                                        filters={"parent": user_kyc.name},
                                        fields="*",
                                    )
                                    for b in bank_account_list:
                                        other_bank = frappe.get_doc(
                                            "User Bank Account", b.name
                                        )
                                        if other_bank.is_default == 1:
                                            other_bank.is_default = 0
                                            other_bank.save(ignore_permissions=True)

                                    frappe.delete_doc(
                                        "User Bank Account", bank_entry_name
                                    )

                                    frappe.get_doc(
                                        {
                                            "doctype": "User Bank Account",
                                            "parentfield": "bank_account",
                                            "parenttype": "User KYC",
                                            "bank": data.get("bank"),
                                            "branch": data.get("branch"),
                                            "account_type": data.get(
                                                "bank_account_type"
                                            ),
                                            "account_number": result_.get(
                                                "accountNumber"
                                            ),
                                            "ifsc": data.get("ifsc"),
                                            "account_holder_name": data.get(
                                                "account_holder_name"
                                            ),
                                            "personalized_cheque": photos_,
                                            "city": data.get("city"),
                                            "parent": user_kyc.name,
                                            "is_default": True,
                                            "bank_status": "Pending",
                                            "penny_request_id": res_json.get(
                                                "body"
                                            ).get("request_id"),
                                            "bank_transaction_status": result_.get(
                                                "bankTxnStatus"
                                            ),
                                        }
                                    ).insert(ignore_permissions=True)
                                    frappe.db.commit()

                            else:
                                # For non choice user
                                frappe.get_doc(
                                    {
                                        "doctype": "User Bank Account",
                                        "parentfield": "bank_account",
                                        "parenttype": "User KYC",
                                        "bank": data.get("bank"),
                                        "branch": data.get("branch"),
                                        "account_type": data.get("bank_account_type"),
                                        "account_number": result_.get("accountNumber"),
                                        "ifsc": data.get("ifsc"),
                                        "account_holder_name": data.get(
                                            "account_holder_name"
                                        ),
                                        "personalized_cheque": photos_,
                                        "city": data.get("city"),
                                        "parent": user_kyc.name,
                                        "is_default": True,
                                        "bank_status": "Pending",
                                        "penny_request_id": res_json.get("body").get(
                                            "request_id"
                                        ),
                                        "bank_transaction_status": result_.get(
                                            "bankTxnStatus"
                                        ),
                                    }
                                ).insert(ignore_permissions=True)
                                frappe.db.commit()
                            return utils.respondWithSuccess(
                                message="Your account details have been successfully verified"
                            )
                    else:
                        lms.log_api_error(mess=str(res_json))
                        return utils.respondWithFailure(
                            status=417,
                            message=result_.get("bankResponse"),
                        )
                else:
                    lms.log_api_error(mess=str(res_json))
                    return utils.respondWithFailure(
                        status=417,
                        message="Your bank account details are not verified, please try again after sometime.",
                    )
            else:
                lms.log_api_error(mess=str(res_json))
                return utils.respondWithFailure(
                    status=res_json.get("status_code"),
                    message=res_json.get("message"),
                )

    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()
