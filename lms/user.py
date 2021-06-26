import base64
import json
import re
import time
from datetime import MINYEAR, date, datetime, timedelta
from time import gmtime

import frappe
import pandas as pd
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.utils.password import check_password, update_password

import lms

# from lms.exceptions.UserKYCNotFoundException import UserKYCNotFoundException
# from lms.exceptions.UserNotFoundException import UserNotFoundException
from lms.exceptions import *
from lms.firebase import FirebaseAdmin


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

        frappe.db.begin()
        update_password(frappe.session.user, data.get("pin"))
        frappe.db.commit()

        doc = frappe.get_doc("User", frappe.session.user)
        # mess = frappe._(
        #     "Dear "
        #     + doc.full_name
        #     + ", You have successfully updated your Finger Print / PIN registration at Spark.Loans!."
        # )
        mess = frappe._(
            "You have successfully updated your Finger Print / PIN registration at Spark.Loans!."
        )
        frappe.enqueue(method=send_sms, receiver_list=[doc.phone], msg=mess)

        return utils.respondWithSuccess(message=frappe._("User PIN has been set"))
    except utils.APIException as e:
        frappe.db.rollback()
        return e.respond()


@frappe.whitelist()
def kyc(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {
                "pan_no": "required",
                "birth_date": "required",
                "accept_terms": ["required", "between:0,1", "decimal"],
            },
        )

        try:
            datetime.strptime(data.get("birth_date"), "%d-%m-%Y")
        except ValueError:
            return utils.respondWithFailure(
                status=417,
                message=frappe._("Incorrect date format, should be DD-MM-YYYY"),
            )

        reg = lms.regex_special_characters(search=data.get("pan_no"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        try:
            user_kyc = lms.__user_kyc(frappe.session.user, data.get("pan_no"))
        except UserKYCNotFoundException:
            user_kyc = None

        if not user_kyc:

            if not data.get("accept_terms"):
                return utils.respondUnauthorized(
                    message=frappe._("Please accept Terms and Conditions.")
                )

            user = lms.__user()

            frappe.db.begin()
            # save user kyc consent
            kyc_consent_doc = frappe.get_doc(
                {
                    "doctype": "User Consent",
                    "mobile": user.phone,
                    "consent": "Kyc",
                }
            )
            kyc_consent_doc.insert(ignore_permissions=True)

            res = get_choice_kyc(data.get("pan_no"), data.get("birth_date"))
            user_kyc = res["user_kyc"]
            customer = lms.__customer()
            customer.kyc_update = 1
            customer.choice_kyc = user_kyc.name
            customer.save(ignore_permissions=True)
            frappe.db.commit()

            """changes as per latest email notification list-sent by vinayak - email verification final 2.0"""
            # frappe.enqueue_doc("Notification", "User KYC", method="send", doc=user)

            # mess = frappe._(
            #     "Dear "
            #     + user.full_name
            #     + ",\nCongratulations! \nYour KYC verification is completed. \nYour credit check has to be cleared by our lending partner before you can avail the loan."
            # )
            # mess = frappe._(
            #     "Congratulations! \nYour KYC verification is completed. \nYour credit check has to be cleared by our lending partner before you can avail the loan."
            # )
            mess = frappe._(
                # "Dear Customer,\nCongratulations! Your KYC verification is completed. -Spark Loans"
                "Dear Customer, \nCongratulations! \nYour KYC verification is completed.  -Spark Loans"
            )
            frappe.enqueue(method=send_sms, receiver_list=[user.phone], msg=mess)

        data = {"user_kyc": user_kyc}

        return utils.respondWithSuccess(data=data)
    except utils.APIException as e:
        frappe.db.rollback()
        return e.respond()


def get_choice_kyc(pan_no, birth_date):
    try:
        las_settings = frappe.get_single("LAS Settings")

        params = {
            "PANNum": pan_no,
            "dob": (datetime.strptime(birth_date, "%d-%m-%Y")).strftime("%Y-%m-%d"),
        }

        headers = {
            "businessUnit": las_settings.choice_business_unit,
            "userId": las_settings.choice_user_id,
            "investorId": las_settings.choice_investor_id,
            "ticket": las_settings.choice_ticket,
        }

        res = requests.get(las_settings.choice_pan_api, params=params, headers=headers)

        data = res.json()

        if not res.ok or "errorCode" in data:
            raise UserKYCNotFoundException
            raise utils.APIException(res.text)

        user_kyc = lms.__user_kyc(pan_no=pan_no, throw=False)
        user_kyc.kyc_type = "CHOICE"
        user_kyc.investor_name = data["investorName"]
        user_kyc.father_name = data["fatherName"]
        user_kyc.mother_name = data["motherName"]
        user_kyc.address = data["address"].replace("~", " ")
        user_kyc.city = data["addressCity"]
        user_kyc.state = data["addressState"]
        user_kyc.pincode = data["addressPinCode"]
        user_kyc.mobile_number = data["mobileNum"]
        user_kyc.choice_client_id = data["clientId"]
        user_kyc.pan_no = data["panNum"]
        user_kyc.date_of_birth = datetime.strptime(
            data["dateOfBirth"], "%Y-%m-%dT%H:%M:%S.%f%z"
        ).strftime("%Y-%m-%d")

        if data["banks"]:
            user_kyc.bank_account = []

            for bank in data["banks"]:
                user_kyc.append(
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
                    },
                )
        user_kyc.save(ignore_permissions=True)

        return {
            "user_kyc": user_kyc,
        }

    except requests.RequestException as e:
        raise utils.APIException(str(e))
    except UserKYCNotFoundException:
        raise
    except Exception as e:
        raise utils.APIException(str(e))


@frappe.whitelist()
def securities(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {
                "lender": "",
            },
        )
        reg = lms.regex_special_characters(search=data.get("lender"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        if not data.get("lender", None):
            data["lender"] = frappe.get_last_doc("Lender").name

        user_kyc = lms.__user_kyc()

        las_settings = frappe.get_single("LAS Settings")

        # get securities list from choice
        payload = {"UserID": las_settings.choice_user_id, "ClientID": user_kyc.pan_no}

        try:
            res = requests.post(
                las_settings.choice_securities_list_api,
                json=payload,
                headers={"Accept": "application/json"},
            )
            if not res.ok:
                raise utils.APIException(res.text)

            res_json = res.json()
            if res_json["Status"] != "Success":
                raise utils.APIException(res.text)

            # setting eligibility
            # securities_list = res_json["Response"]
            securities_list = [i for i in res_json["Response"] if i.get("Price") > 0]
            securities_list_ = [i["ISIN"] for i in securities_list]
            securities_category_map = lms.get_allowed_securities(
                securities_list_, data.get("lender")
            )

            for i in securities_list:
                try:
                    i["Category"] = securities_category_map[i["ISIN"]].get(
                        "security_category"
                    )
                    i["Is_Eligible"] = True
                except KeyError:
                    i["Is_Eligible"] = False
                    i["Category"] = None

            return utils.respondWithSuccess(data=securities_list)
        except requests.RequestException as e:
            raise utils.APIException(str(e))
    except utils.APIException as e:
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


@frappe.whitelist()
def dashboard_old():
    customer = lms.__customer()
    pending_loan_applications = frappe.get_all(
        "Loan Application",
        filters={"customer": customer.name, "status": "Pledge accepted by Lender"},
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
        pending_esigns=pending_esigns,
    )
    return utils.respondWithSuccess(message=frappe._("Success"), data=token)


@frappe.whitelist()
def approved_securities(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {
                "lender": "",
                "start": "decimal|min:0",
                "per_page": "decimal|min:0",
                "search": "",
                "category": "",
                "is_download": "decimal|between:0,1",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("lender") + data.get("category")
        )
        search_reg = lms.regex_special_characters(
            search=data.get("search"), regex=re.compile("[@!#$%_^&*<>?/\|}{~`]")
        )
        if reg or search_reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        if isinstance(data.get("is_download"), str):
            data["is_download"] = int(data.get("is_download"))

        if not data.get("lender"):
            data["lender"] = frappe.get_last_doc("Lender").name

        filters = {"lender": data.get("lender")}

        security_category_list_ = frappe.db.get_all(
            "Allowed Security",
            filters=filters,
            fields=["distinct(security_category)"],
            order_by="security_category asc",
        )
        security_category_list = [i.security_category for i in security_category_list_]

        or_filters = ""
        if data.get("search", None):
            search_key = ["like", str("%" + data["search"] + "%")]
            or_filters = {"security_name": search_key}

        if data.get("category", None):
            filters["security_category"] = data.get("category")

        approved_security_list = []
        approved_security_pdf_file_url = ""

        if data.get("is_download"):
            approved_security_list = frappe.db.get_all(
                "Allowed Security",
                filters=filters,
                or_filters=or_filters,
                order_by="security_name asc",
                fields=[
                    "isin",
                    "security_name",
                    "security_category",
                    "eligible_percentage",
                ],
            )
            approved_security_list.sort(
                key=lambda item: (item["security_name"]).title()
            )

            if not approved_security_list:
                return utils.respondNotFound(message=_("No Record Found"))

            lt_list = []

            for list in approved_security_list:
                lt_list.append(list.values())
            df = pd.DataFrame(lt_list)
            df.columns = approved_security_list[0].keys()
            df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()
            df.index += 1
            approved_security_pdf_file = "{}-approved-securities.pdf".format(
                data.get("lender")
            ).replace(" ", "-")

            approved_security_pdf_file_path = frappe.utils.get_files_path(
                approved_security_pdf_file
            )

            pdf_file = open(approved_security_pdf_file_path, "wb")
            a = df.to_html()
            style = """<style>
				tr {
				page-break-inside: avoid;
				}
				th {text-align: center;}
				</style>
				"""
            html_with_style = style + a

            from frappe.utils.pdf import get_pdf

            pdf = get_pdf(html_with_style)
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

            approved_security_list = frappe.db.get_all(
                "Allowed Security",
                filters=filters,
                or_filters=or_filters,
                order_by="security_name asc",
                fields=[
                    "isin",
                    "security_name",
                    "security_category",
                    "eligible_percentage",
                ],
                start=data.get("start"),
                page_length=data.get("per_page"),
            )

        res = {
            "security_category_list": security_category_list,
            "approved_securities_list": approved_security_list,
            "pdf_file_url": approved_security_pdf_file_url,
        }

        return utils.respondWithSuccess(data=res)

    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def all_loans_list(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        customer = lms.__customer()
        if not customer:
            return utils.respondNotFound(message=frappe._("Customer not found."))

        all_loans = frappe.get_all(
            "Loan", filters={"customer": customer.name}, order_by="creation desc"
        )

        return utils.respondWithSuccess(data=all_loans)

    except utils.exceptions.APIException as e:
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
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )
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
            return utils.respondNotFound(message=frappe._("Loan not found."))

        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

        if not customer:
            return utils.respondNotFound(message=frappe._("Customer not found."))

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
                }
            )
        all_pledged_securities.sort(key=lambda item: item["security_name"])

        res = {
            "loan_name": loan.name,
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

        res["increase_loan"] = None
        if existing_loan_application[0]["in_process"] == 0:
            res["increase_loan"] = 1

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
            res["unpledge"] = dict(
                unpledge_msg_while_margin_shortfall="""OOPS! Dear {}, It seems you have a margin shortfall. You cannot unpledge any of the pledged securities until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                    loan.get_customer().first_name
                )
                if loan_margin_shortfall
                else None,
                unpledge=loan.max_unpledge_amount(),
            )

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def dashboard(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        try:
            user_kyc = lms.__user_kyc()
        except UserKYCNotFoundException:
            user_kyc = None

        customer = lms.__customer()
        if not customer:
            return utils.respondNotFound(message=frappe._("Customer not found."))

        # all_mgloans = frappe.db.sql(
        #     """select loan.name, loan.drawing_power, loan.drawing_power_str, loan.balance, loan.balance_str,
        # IFNULL(mrgloan.shortfall_percentage, 0.0) as shortfall_percentage, IFNULL(mrgloan.shortfall, 0.0) as shortfall
        # from `tabLoan` as loan
        # left join `tabLoan Margin Shortfall` as mrgloan
        # on loan.name = mrgloan.loan
        # where loan.customer = '{}'
        # and (mrgloan.status = "Pending" or mrgloan.status = "Sell Triggered" or mrgloan.status = "Request Pending")
        # and shortfall_percentage > 0.0
        # group by loan.name""".format(
        #         customer.name
        #     ),
        #     as_dict=1,
        # )

        # all_interest_loans = frappe.db.sql(
        #     """select loan.name, loan.drawing_power, loan.drawing_power_str, loan.balance, loan.balance_str,
        # sum(loantx.unpaid_interest) as interest_amount
        # from `tabLoan` as loan
        # left join `tabLoan Transaction` as loantx
        # on loan.name = loantx.loan
        # where loan.customer = '{}'
        # and loantx.transaction_type in ('Interest','Additional Interest','Penal Interest')
        # and loantx.unpaid_interest > 0
        # group by loan.name""".format(
        #         customer.name
        #     ),
        #     as_dict=1,
        # )

        # actionable_loans = []
        # action_loans = []
        mgloan = []
        deadline_for_all_mg_shortfall = {}
        total_int_amt_all_loans = 0
        due_date_for_all_interest = []
        interest_loan_list = []
        margin_shortfall_and_interest_loans = (
            lms.user.margin_shortfall_and_interest_loans(customer)
        )

        for dictionary in margin_shortfall_and_interest_loans[0]:
            # actionable_loans.append(
            #     {
            #         "loan_name": dictionary.get("name"),
            #         "drawing_power": dictionary.get("drawing_power"),
            #         "drawing_power_str": dictionary.get("drawing_power_str"),
            #         "balance": dictionary.get("balance"),
            #         "balance_str": dictionary.get("balance_str"),
            #     }
            # )
            # action_loans.append(dictionary.get("name"))
            loan = frappe.get_doc("Loan", dictionary["name"])
            mg_shortfall_doc = loan.get_margin_shortfall()
            # mg_shortfall_doc = frappe.get_all("Loan Margin Shortfall", filters={"loan": dictionary["name"], "status":["in", ["Pending", "Sell Triggered"]]}, fields=["*"])[0]
            mg_shortfall_action = frappe.get_doc(
                "Margin Shortfall Action", mg_shortfall_doc.margin_shortfall_action
            )
            if mg_shortfall_doc:
                hrs_difference = mg_shortfall_doc.deadline - frappe.utils.now_datetime()
                if mg_shortfall_action.sell_off_after_hours:
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
                    holidays = date_array.intersection(set(holiday_list()))
                    hrs_difference = (
                        mg_shortfall_doc.deadline
                        - frappe.utils.now_datetime()
                        - timedelta(days=(len(holidays) if holidays else 0))
                    )

                mgloan.append(
                    {
                        "name": dictionary["name"],
                        "deadline": convert_sec_to_hh_mm_ss(
                            abs(hrs_difference).total_seconds()
                        )
                        if mg_shortfall_doc.deadline > frappe.utils.now_datetime()
                        else "00:00:00",
                        "status": dictionary["status"],
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
            # if dictionary.get("name") not in action_loans:
            #     actionable_loans.append(
            #         {
            #             "loan_name": dictionary.get("name"),
            #             "drawing_power": dictionary.get("drawing_power"),
            #             "drawing_power_str": dictionary.get("drawing_power_str"),
            #             "balance": dictionary.get("balance"),
            #             "balance_str": dictionary.get("balance_str"),
            #         }
            #     )

            if dictionary["interest_amount"]:
                loan = frappe.get_doc("Loan", dictionary.get("name"))
                current_date = frappe.utils.now_datetime()
                due_date = ""
                due_date_txt = "Pay By"
                info_msg = ""

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

        ## Under process loan application ##
        # under_process_la = frappe.get_all(
        #     "Loan Application",
        #     filters={
        #         "customer": customer.name,
        #         "status": ["not IN", ["Approved", "Rejected", "Pledge Failure"]],
        #         "pledge_status": ["!=", "Failure"],
        #     },
        #     fields=["name", "status"],
        # )

        # ## Active loans ##
        # active_loans = frappe.get_all(
        #     "Loan",
        #     filters={
        #         "customer": customer.name,
        #         "name": ["not in", [list["loan_name"] for list in actionable_loans]],
        #     },
        #     fields=[
        #         "name",
        #         "drawing_power",
        #         "drawing_power_str",
        #         "balance",
        #         "balance_str",
        #     ],
        # )

        # pending esign object for loan application and topup application
        pending_loan_applications = frappe.get_all(
            "Loan Application",
            filters={"customer": customer.name, "status": "Pledge accepted by Lender"},
            fields=["*"],
        )

        la_pending_esigns = []
        if pending_loan_applications:
            for loan_application in pending_loan_applications:
                loan_application_doc = frappe.get_doc(
                    "Loan Application", loan_application.name
                )

                mess = (
                    "Congratulations! Your application is being considered favourably by our lending partner and finally accepted at Rs. {current_total_collateral_value} against the request value of Rs. {requested_total_collateral_value}. Accordingly, the increase in the sanctioned limit is Rs. {drawing_power}. Please e-sign the loan agreement to avail the increased sanctioned limit now.".format(
                        current_total_collateral_value=loan_application_doc.total_collateral_value,
                        requested_total_collateral_value=loan_application_doc.pledged_total_collateral_value,
                        drawing_power=loan_application_doc.drawing_power,
                    )
                    if loan_application_doc.loan
                    and not loan_application_doc.loan_margin_shortfall
                    else "Congratulations! Your application is being considered favourably by our lending partner and finally accepted at Rs. {current_total_collateral_value} against the request value of Rs. {requested_total_collateral_value}. Accordingly the final Sanctioned Limit is Rs. {drawing_power}. Please e-sign the loan agreement to avail the loan now.".format(
                        current_total_collateral_value=loan_application_doc.total_collateral_value,
                        requested_total_collateral_value=loan_application_doc.pledged_total_collateral_value,
                        drawing_power=loan_application_doc.drawing_power,
                    )
                )
                if (
                    loan_application_doc.loan
                    and not loan_application_doc.loan_margin_shortfall
                ):
                    loan = frappe.get_doc("Loan", loan_application_doc.loan)

                    increase_loan_mess = dict(
                        existing_limit=loan.sanctioned_limit,
                        existing_collateral_value=loan.total_collateral_value,
                        new_limit=(
                            lms.round_down_amount_to_nearest_thousand(
                                (
                                    loan_application_doc.total_collateral_value
                                    + loan.total_collateral_value
                                )
                                * loan_application_doc.allowable_ltv
                                / 100
                            )
                        ),
                        new_collateral_value=loan_application_doc.total_collateral_value
                        + loan.total_collateral_value,
                    )

                la_pending_esigns.append(
                    {
                        "loan_application": loan_application_doc,
                        "message": mess,
                        "increase_loan_message": increase_loan_mess
                        if loan_application_doc.loan
                        and not loan_application_doc.loan_margin_shortfall
                        else None,
                    }
                )

        pending_topup_applications = frappe.get_all(
            "Top up Application",
            filters={"customer": customer.name, "status": "Pending"},
            fields=["*"],
        )

        topup_pending_esigns = []
        if pending_topup_applications:
            for topup_application in pending_topup_applications:
                topup_application_doc = frappe.get_doc(
                    "Top up Application", topup_application.name
                ).as_dict()

                topup_application_doc.top_up_amount = lms.amount_formatter(
                    topup_application_doc.top_up_amount
                )

                # topup_tnc = frappe.get_all(
                #     "Approved Terms and Conditions",
                #     filters={"application_name": topup_application.name},
                # )
                topup_pending_esigns.append(
                    {
                        "topup_application_doc": topup_application_doc,
                        "mess": "Congratulations! Your application is being considered favourably by our lending partner. Accordingly, the increase in the sanctioned limit is Rs. {}. Please e-sign the loan agreement to avail the increased sanctioned limit now.".format(
                            topup_application_doc.top_up_amount
                        )
                        # "is_topup_tnc_done": 1 if topup_tnc else 0,
                    }
                )

        pending_esigns_list = dict(
            la_pending_esigns=la_pending_esigns,
            topup_pending_esigns=topup_pending_esigns,
        )

        ## Topup ##
        # topup = None
        # topup_list = []
        # sell_collateral_list = []
        # increase_loan_list = []
        # unpledge_application_list = []
        # all_loans = frappe.get_all("Loan", filters={"customer": customer.name})

        # for loan in all_loans:
        # loan = frappe.get_doc("Loan", loan.name)
        # existing_topup_application = frappe.get_all(
        #     "Top up Application",
        #     filters={
        #         "loan": loan.name,
        #         "customer": customer.name,
        #         "status": ["not IN", ["Approved", "Rejected"]],
        #     },
        #     fields=["count(name) as in_process"],
        # )

        # if existing_topup_application[0]["in_process"] == 0:
        #     topup = loan.max_topup_amount()
        #     if topup:
        #         top_up = {
        #             "loan": loan.name,
        #             "top_up_amount": topup,
        #         }
        #         topup_list.append(top_up)
        #     else:
        #         top_up = None

        # # Sell Collateral
        # sell_collateral_application_exist = frappe.get_all(
        #     "Sell Collateral Application",
        #     filters={"loan": loan.name, "status": "Pending"},
        #     fields=[
        #         "name",
        #         "creation",
        #         "modified",
        #         "modified_by",
        #         "owner",
        #         "docstatus",
        #         "parent",
        #         "parentfield",
        #         "parenttype",
        #         "idx",
        #         "loan",
        #         "total_collateral_value",
        #         "lender",
        #         "customer",
        #         "selling_collateral_value",
        #         "amended_from",
        #         "status",
        #         "workflow_state",
        #         "loan_margin_shortfall",
        #     ],
        #     order_by="creation desc",
        #     page_length=1,
        # )
        # if sell_collateral_application_exist:
        #     sell_collateral_application_exist[0]["items"] = frappe.get_all(
        #         "Sell Collateral Application Item",
        #         filters={"parent": sell_collateral_application_exist[0].name},
        #         fields=["*"],
        #     )

        # sell_collateral_list.append(
        #     {
        #         "loan_name": loan.name,
        #         "sell_collateral_available": sell_collateral_application_exist[0]
        #         if len(sell_collateral_application_exist)
        #         else None,
        #     }
        # )

        # Increase Loan
        # existing_loan_application = frappe.get_all(
        #     "Loan Application",
        #     filters={
        #         "loan": loan.name,
        #         "customer": loan.customer,
        #         "status": ["not IN", ["Approved", "Rejected"]],
        #     },
        #     fields=["count(name) as in_process"],
        # )

        # increase_loan_list.append(
        #     {
        #         "loan_name": loan.name,
        #         "increase_loan_available": 1
        #         if existing_loan_application[0]["in_process"] == 0
        #         else None,
        #     }
        # )

        # check if any pending unpledge application exist
        #     loan_margin_shortfall = loan.get_margin_shortfall()
        #     if loan_margin_shortfall.get("__islocal", None):
        #         loan_margin_shortfall = None
        #     unpledge_application_exist = frappe.get_all(
        #         "Unpledge Application",
        #         filters={"loan": loan.name, "status": "Pending"},
        #         fields=[
        #             "name",
        #             "creation",
        #             "modified",
        #             "modified_by",
        #             "owner",
        #             "docstatus",
        #             "parent",
        #             "parentfield",
        #             "parenttype",
        #             "idx",
        #             "loan",
        #             "total_collateral_value",
        #             "lender",
        #             "customer",
        #             "unpledge_collateral_value",
        #             "amended_from",
        #             "status",
        #             "workflow_state",
        #         ],
        #         order_by="creation desc",
        #         page_length=1,
        #     )
        #     if unpledge_application_exist:
        #         unpledge_application_exist[0]["items"] = frappe.get_all(
        #             "Unpledge Application Item",
        #             filters={"parent": unpledge_application_exist[0].name},
        #             fields=["*"],
        #         )

        #     unpledge_application_list.append(
        #         {
        #             "loan_name": loan.name,
        #             "unpledge_application_available": unpledge_application_exist[0]
        #             if unpledge_application_exist
        #             else None,
        #             "unpledge_msg_while_margin_shortfall": """OOPS! Dear {}, It seems you have a margin shortfall. You cannot unpledge any of the pledged securities until the margin shortfall is made good. Go to: Margin Shortfall""".format(
        #                 loan.get_customer().first_name
        #             )
        #             if loan_margin_shortfall
        #             else None,
        #             "unpledge": None
        #             if unpledge_application_exist or loan_margin_shortfall
        #             else loan.max_unpledge_amount(),
        #         }
        #     )

        # topup_list.sort(key=lambda item: (item["loan"]), reverse=True)
        # sell_collateral_list.sort(key=lambda item: (item["loan_name"]), reverse=True)
        # increase_loan_list.sort(key=lambda item: (item["loan_name"]), reverse=True)
        # unpledge_application_list.sort(
        #     key=lambda item: (item["loan_name"]), reverse=True
        # )

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

        res = {
            "customer": customer,
            "user_kyc": user_kyc,
            "margin_shortfall_card": deadline_for_all_mg_shortfall,
            "total_interest_all_loans_card": total_interest_all_loans,
            # "under_process_la": under_process_la,
            # "actionable_loans": actionable_loans,
            # "active_loans": active_loans,
            "pending_esigns_list": pending_esigns_list,
            # "top_up": topup_list,
            # "sell_collateral_list": sell_collateral_list,
            # "increase_loan_list": increase_loan_list,
            # "unpledge_application_list": unpledge_application_list,
            "show_feedback_popup": show_feedback_popup,
        }

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def weekly_pledged_security_dashboard(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        customer = lms.__customer()
        if not customer:
            return utils.respondNotFound(message=frappe._("Customer not found."))

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
        # all_isin_dict = {i.isin: i.total_pledged_qty for i in all_loan_items}
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
        weekly_security_amount.sort(
            key=lambda item: (item["week"]), reverse=True
        )
        return utils.respondWithSuccess(data=weekly_security_amount)

    except utils.exceptions.APIException as e:
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

        # alerts percentage and amount save in doctype
        if (
            data.get("is_for_alerts")
            and not data.get("percentage")
            and not data.get("amount")
        ):
            return utils.respondWithFailure(
                status=417,
                message=frappe._(
                    "Please select Amount or Percentage for setting Alerts"
                ),
            )

        elif (
            data.get("is_for_alerts") and data.get("percentage") and data.get("amount")
        ):
            return utils.respondWithFailure(
                status=417,
                message=frappe._(
                    "Please choose one between Amount or Percentage for setting Alerts"
                ),
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

        res = {
            "customer_details": customer,
            "user_kyc": user_kyc,
            "last_login": last_login_time,
        }

        return utils.respondWithSuccess(data=res)
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def update_profile_pic_and_pin(**kwargs):
    try:
        # validation
        utils.validator.validate_http_method("POST")
        user = lms.__user()

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
            data["image"] = bytes(data.get("image")[1:-1], encoding="utf8")

        if isinstance(data.get("is_for_update_pin"), str):
            data["is_for_update_pin"] = int(data.get("is_for_update_pin"))

        if data.get("is_for_profile_pic") and data.get("image"):
            profile_picture_file = "{}-profile-picture.jpeg".format(
                user.full_name
            ).replace(" ", "-")

            profile_picture_file_path = frappe.utils.get_files_path(
                profile_picture_file
            )

            image_decode = base64.decodestring(data.get("image"))
            image_file = open(profile_picture_file_path, "wb").write(image_decode)

            profile_picture_file_url = frappe.utils.get_url(
                "files/{}-profile-picture.jpeg".format(user.full_name).replace(" ", "-")
            )
            # user.user_image = 0
            # user.user_image = profile_picture_file_url
            # user.save(ignore_permissions=True)
            # frappe.db.commit()
            return utils.respondWithSuccess(
                data={"profile_picture_file_url": profile_picture_file_url}
            )

        elif data.get("is_for_profile_pic") and not data.get("image"):
            return utils.respondWithFailure(
                status=417, message=frappe._("Please upload image.")
            )

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
                return utils.respondWithFailure(
                    status=417, message=frappe._("Incorrect User or Password.")
                )

            if old_pass_check:
                if data.get("retype_pin") == data.get("new_pin") and data.get(
                    "old_pin"
                ) != data.get("new_pin"):
                    # update pin
                    update_password(frappe.session.user, data.get("retype_pin"))
                    frappe.db.commit()
                elif data.get("old_pin") == data.get("new_pin"):
                    return utils.respondWithFailure(
                        status=417,
                        message=frappe._("Dont put new pin same as old pin."),
                    )
                else:
                    return utils.respondWithFailure(
                        status=417, message=frappe._("Please retype correct pin.")
                    )

            return utils.respondWithSuccess(
                message=frappe._("User PIN has been updated.")
            )

        elif data.get("is_for_update_pin") and (
            not data.get("old_pin") or not data.get("new_pin")
        ):
            return utils.respondWithFailure(
                status=417, message=frappe._("Please Enter old pin and new pin.")
            )

    except utils.APIException:
        frappe.db.rollback()


@frappe.whitelist(allow_guest=True)
def contact_us(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs, {"search": "", "view_more": "decimal|between:0,1"}
        )

        reg = lms.regex_special_characters(
            search=data.get("search"), regex=re.compile("[@!#$%_^&*<>?/\|}{~`]")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        if isinstance(data.get("view_more"), str):
            data["view_more"] = int(data.get("view_more"))

        filters_arr = {}
        if data.get("view_more") or data.get("search"):
            # all FAQ will be shown
            page_length = ""
        else:
            # only recent 6 FAQ will be shown
            page_length = 6

        if data.get("search", None):
            search_key = str("%" + data["search"] + "%")
            filters_arr = {
                "topic": ["like", search_key],
                "description": ["like", search_key],
                "resolution": ["like", search_key],
            }

        faq = frappe.get_all(
            "FAQ", or_filters=filters_arr, fields=["*"], page_length=page_length
        )

        if not faq:
            return utils.respondWithSuccess(
                message="Your issue does not match with Common Issues. Please Contact Us."
            )

        return utils.respondWithSuccess(data=faq)
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def check_eligible_limit(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"lender": "", "search": ""})

        reg = lms.regex_special_characters(search=data.get("lender"))
        search_reg = lms.regex_special_characters(
            search=data.get("search"), regex=re.compile("[@!#$%_^&*<>?/\|}{~`]")
        )
        if reg or search_reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        if not data.get("lender"):
            data["lender"] = frappe.get_last_doc("Lender").name

        eligible_limit_list = frappe.db.sql(
            """
			SELECT
			als.security_name as Scrip_Name, als.eligible_percentage, als.lender, als.security_category as Category, s.price as Price
			FROM `tabAllowed Security` als
			LEFT JOIN `tabSecurity` s
			ON als.isin = s.isin
			where als.lender = '{}'
            and s.price > 0
			and als.security_name like '%{}%'
            order by als.security_name;
			""".format(
                data.get("lender"), data.get("search")
            ),
            as_dict=1,
        )

        if not eligible_limit_list:
            return utils.respondNotFound(message=_("No Record Found"))

        # for i in eligible_limit_list:
        #     i["Is_Eligible"] = True
        list = map(lambda item: dict(item, Is_Eligible=True), eligible_limit_list)

        return utils.respondWithSuccess(data=list)
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def all_lenders_list(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        all_lenders = frappe.get_all("Lender", order_by="creation desc")

        return utils.respondWithSuccess(data=all_lenders)

    except utils.exceptions.APIException as e:
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
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

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

        # validation
        # if data.get("do_not_show_again") or customer.feedback_submitted:
        #     return utils.respondWithFailure(
        #         message=frappe._("Dont show feedback popup again")
        #     )
        if not data.get("do_not_show_again"):
            if (data.get("bulls_eye") and data.get("can_do_better")) or (
                not data.get("bulls_eye") and not data.get("can_do_better")
            ):
                return utils.respondWithFailure(
                    status=417,
                    message=frappe._("Please select atleast one option."),
                )

            if (
                data.get("can_do_better")
                and not data.get("related_to_user_experience")
                and not data.get("related_to_functionality")
                and not data.get("others")
            ):
                return utils.respondWithFailure(
                    status=417,
                    message=frappe._("Please select atleast one from below options."),
                )

            # if not data.get("do_not_show_again") or not customer.feedback_submitted:
            if not data.get("comment") or data.get("comment").isspace():
                return utils.respondWithFailure(
                    message=frappe._("Please write your suggestion to us.")
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

        # if number_of_user_login[0].status_count > 10:
        # show feedback popup
        # number_of_user_login = frappe.db.count(
        #     "User Token",
        #     filters={"token_type": "Firebase Token", "entity": customer.user},
        # )
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
                    "doctype": "Feedback",
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
            # feedback_already_given = frappe.get_doc(
            #     "Feedback", {"customer": customer.name}
            # )
            # if feedback_already_given:
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
            return utils.respondWithFailure(
                status=417, message=frappe._("Oops something went wrong.")
            )
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def loan_summary_dashboard(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        try:
            user_kyc = lms.__user_kyc()
        except UserKYCNotFoundException:
            user_kyc = None

        customer = lms.__customer()
        if not customer:
            return utils.respondNotFound(message=frappe._("Customer not found."))

        mindate = datetime(MINYEAR, 1, 1)
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
            # else:
            sell_collateral_list.append(
                {
                    "loan_name": loan.name,
                    "sell_collateral_available": sell_collateral_application_exist[0]
                    if sell_collateral_application_exist
                    else None,
                }
            )

            loan_margin_shortfall = loan.get_margin_shortfall()
            if loan_margin_shortfall.get("__islocal", None):
                loan_margin_shortfall = None
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
                unpledge_list.append(
                    {
                        "loan_name": loan.name,
                        # "creation": mindate,
                        "unpledge_application_available": None,
                        "unpledge_msg_while_margin_shortfall": """OOPS! Dear {}, It seems you have a margin shortfall. You cannot unpledge any of the pledged securities until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                            loan.get_customer().first_name
                        )
                        if loan_margin_shortfall
                        else None,
                        "unpledge": None
                        if unpledge_application_exist or loan_margin_shortfall
                        else loan.max_unpledge_amount(),
                        # "sell_collateral_available": None,
                        # "top_up_amount": 0.0,
                        # "existing_topup_application": None
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

        res = {
            "sell_collateral_topup_and_unpledge_list": sell_collateral_topup_and_unpledge_list,
            "actionable_loan": actionable_loan,
            "under_process_la": under_process_la,
            "active_loans": active_loans,
            "sell_collateral_list": sell_collateral_list,
            "unpledge_list": unpledge_list,
            "topup_list": topup_list,
            "increase_loan_list": increase_loan_list,
        }

        return utils.respondWithSuccess(data=res)

    except utils.exceptions.APIException as e:
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


def convert_sec_to_hh_mm_ss(seconds):
    min, sec = divmod(seconds, 60)
    hour, min = divmod(min, 60)
    return "%d:%02d:%02d" % (hour, min, sec)


def holiday_list():
    date_list = []
    holiday_list = frappe.get_all("Bank Holiday", "date", order_by="date asc")
    for i, dates in enumerate(d["date"] for d in holiday_list):
        date_list.append(dates)

    return list(set(date_list))
