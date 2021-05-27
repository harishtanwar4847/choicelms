import json
import math
import re
from datetime import date, datetime, timedelta

import frappe
import pandas as pd
import requests
import utils
from frappe import _
from utils.responder import respondWithFailure, respondWithSuccess

import lms
from lms.user import convert_sec_to_hh_mm_ss, holiday_list


@frappe.whitelist()
def esign_old(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_application_name": "required",
            },
        )

        customer = lms.__customer()
        loan_application = frappe.get_doc(
            "Loan Application", data.get("loan_application_name")
        )
        if not loan_application:
            return utils.respondNotFound(message=_("Loan Application not found."))
        if loan_application.customer != customer.name:
            return utils.respondForbidden(
                message=_("Please use your own Loan Application.")
            )

        user = lms.__user()

        esign_request = loan_application.esign_request()
        try:
            res = requests.post(
                esign_request.get("file_upload_url"),
                files=esign_request.get("files"),
                headers=esign_request.get("headers"),
            )

            if not res.ok:
                raise utils.APIException(res.text)

            data = res.json()

            esign_url_dict = esign_request.get("esign_url_dict")
            esign_url_dict["id"] = data.get("id")
            url = esign_request.get("esign_url").format(**esign_url_dict)

            return utils.respondWithSuccess(
                message=_("Esign URL."),
                data={"esign_url": url, "file_id": data.get("id")},
            )
        except requests.RequestException as e:
            raise utils.APIException(str(e))
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def esign(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {"loan_application_name": "", "topup_application_name": ""},
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_application_name")
            + data.get("topup_application_name")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        if data.get("loan_application_name") and data.get("topup_application_name"):
            return utils.respondForbidden(
                message=_("Can not use both application at once, please use one.")
            )
        elif not data.get("loan_application_name") and not data.get(
            "topup_application_name"
        ):
            return utils.respondForbidden(
                message=_(
                    "Loan Application and Top up Application not found. Please use atleast one."
                )
            )
        if data.get("loan_application_name"):
            loan_application = frappe.get_doc(
                "Loan Application", data.get("loan_application_name")
            )
            if not loan_application:
                return utils.respondNotFound(message=_("Loan Application not found."))
            if loan_application.customer != customer.name:
                return utils.respondForbidden(
                    message=_("Please use your own Loan Application.")
                )
            increase_loan = 0
            if loan_application.loan and not loan_application.loan_margin_shortfall:
                increase_loan = 1
            esign_request = loan_application.esign_request(increase_loan)

        else:
            topup_application = frappe.get_doc(
                "Top up Application", data.get("topup_application_name")
            )
            if not topup_application:
                return utils.respondNotFound(message=_("Topup Application not found."))
            if topup_application.customer != customer.name:
                return utils.respondForbidden(
                    message=_("Please use your own Topup Application.")
                )
            esign_request = topup_application.esign_request()

        user = lms.__user()

        try:
            res = requests.post(
                esign_request.get("file_upload_url"),
                files=esign_request.get("files"),
                headers=esign_request.get("headers"),
            )

            if not res.ok:
                raise utils.APIException(res.text)

            data = res.json()

            esign_url_dict = esign_request.get("esign_url_dict")
            esign_url_dict["id"] = data.get("id")
            url = esign_request.get("esign_url").format(**esign_url_dict)

            return utils.respondWithSuccess(
                message=_("Esign URL."),
                data={"esign_url": url, "file_id": data.get("id")},
            )
        except requests.RequestException as e:
            raise utils.APIException(str(e))
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def esign_done(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_application_name": "",
                "topup_application_name": "",
                "file_id": "required",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_application_name")
            + data.get("topup_application_name")
            + data.get("file_id")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        user = lms.__user()
        customer = lms.__customer()
        las_settings = frappe.get_single("LAS Settings")

        if data.get("loan_application_name") and data.get("topup_application_name"):
            return utils.respondForbidden(
                message=_("Can not use both application at once, please use one.")
            )
        elif not data.get("loan_application_name") and not data.get(
            "topup_application_name"
        ):
            return utils.respondForbidden(
                "Loan Application and Top up Application not found. Please use atleast one."
            )

        if data.get("loan_application_name"):
            loan_application = frappe.get_doc(
                "Loan Application", data.get("loan_application_name")
            )
            if not loan_application:
                return utils.respondNotFound(message=_("Loan Application not found."))
            if loan_application.customer != customer.name:
                return utils.respondForbidden(
                    message=_("Please use your own Loan Application.")
                )
            increase_loan = 0
            if loan_application.loan and not loan_application.loan_margin_shortfall:
                increase_loan = 1
            if increase_loan:
                esigned_pdf_url = "{}{}".format(
                    las_settings.esign_host,
                    las_settings.enhancement_esign_download_signed_file_uri,
                ).format(file_id=data.get("file_id"))
            else:
                esigned_pdf_url = "{}{}".format(
                    las_settings.esign_host, las_settings.esign_download_signed_file_uri
                ).format(file_id=data.get("file_id"))

        else:
            topup_application = frappe.get_doc(
                "Top up Application", data.get("topup_application_name")
            )
            if not topup_application:
                return utils.respondNotFound(message=_("Topup Application not found."))
            if topup_application.customer != customer.name:
                return utils.respondForbidden(
                    message=_("Please use your own Topup Application.")
                )
            esigned_pdf_url = "{}{}".format(
                las_settings.esign_host,
                las_settings.enhancement_esign_download_signed_file_uri,
            ).format(file_id=data.get("file_id"))

        try:
            res = requests.get(esigned_pdf_url, allow_redirects=True)
            frappe.db.begin()

            # save e-sign consent
            kyc_consent_doc = frappe.get_doc(
                {
                    "doctype": "User Consent",
                    "mobile": user.phone,
                    "consent": "E-sign",
                }
            )
            kyc_consent_doc.insert(ignore_permissions=True)

            if data.get("loan_application_name"):
                esigned_file = frappe.get_doc(
                    {
                        "doctype": "File",
                        "file_name": "{}-aggrement.pdf".format(
                            data.get("loan_application_name")
                        ),
                        "content": res.content,
                        "attached_to_doctype": "Loan Application",
                        "attached_to_name": data.get("loan_application_name"),
                        "attached_to_field": "customer_esigned_document",
                        "folder": "Home",
                    }
                )
                esigned_file.save(ignore_permissions=True)

                loan_application.status = "Esign Done"
                loan_application.workflow_state = "Esign Done"
                loan_application.customer_esigned_document = esigned_file.file_url
                loan_application.save(ignore_permissions=True)
                frappe.db.commit()
            else:
                esigned_file = frappe.get_doc(
                    {
                        "doctype": "File",
                        "file_name": "{}-aggrement.pdf".format(
                            data.get("topup_application_name")
                        ),
                        "content": res.content,
                        "attached_to_doctype": "Top up Application",
                        "attached_to_name": data.get("topup_application_name"),
                        "attached_to_field": "customer_esigned_document",
                        "folder": "Home",
                    }
                )
                esigned_file.save(ignore_permissions=True)

                topup_application.status = "Esign Done"
                topup_application.workflow_state = "Esign Done"
                topup_application.customer_esigned_document = esigned_file.file_url
                topup_application.save(ignore_permissions=True)
                frappe.db.commit()

            return utils.respondWithSuccess()
        except requests.RequestException as e:
            raise utils.APIException(str(e))
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def my_loans():
    try:
        customer = lms.__customer()
        loans = frappe.db.sql(
            """select
			loan.total_collateral_value, loan.name, loan.sanctioned_limit, loan.drawing_power,

			if ((loan.total_collateral_value * loan.allowable_ltv / 100 - loan.sanctioned_limit) > (loan.sanctioned_limit * 0.1), 1, 0) as top_up_available,

			if ((loan.total_collateral_value * loan.allowable_ltv / 100) - loan.sanctioned_limit > (loan.sanctioned_limit * 0.1),
			loan.total_collateral_value * loan.allowable_ltv / 100 - loan.sanctioned_limit, 0.0) as top_up_amount,

			IFNULL(mrgloan.shortfall_percentage, 0.0) as shortfall_percentage,
			IFNULL(mrgloan.shortfall_c, 0.0) as shortfall_c,
			IFNULL(mrgloan.shortfall, 0.0) as shortfall,

			SUM(COALESCE(CASE WHEN loantx.record_type = 'DR' THEN loantx.amount END,0))
			- SUM(COALESCE(CASE WHEN loantx.record_type = 'CR' THEN loantx.amount END,0)) outstanding

			from `tabLoan` as loan
			left join `tabLoan Margin Shortfall` as mrgloan
			on loan.name = mrgloan.loan
			left join `tabLoan Transaction` as loantx
			on loan.name = loantx.loan
			where loan.customer = '{}' group by loantx.loan """.format(
                customer.name
            ),
            as_dict=1,
        )

        data = {"loans": loans}
        data["total_outstanding"] = float(sum([i.outstanding for i in loans]))
        data["total_sanctioned_limit"] = float(sum([i.sanctioned_limit for i in loans]))
        data["total_drawing_power"] = float(sum([i.drawing_power for i in loans]))
        data["total_total_collateral_value"] = float(
            sum([i.total_collateral_value for i in loans])
        )
        data["total_margin_shortfall"] = float(sum([i.shortfall_c for i in loans]))
        return lms.generateResponse(message=_("Loan"), data=data)

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)


# TODO: review. it has a query for tabLoan Collateral which has been deleted in Beta.1
@frappe.whitelist()
def create_unpledge_old(loan_name, securities_array):
    try:
        lms.validate_http_method("POST")

        if not loan_name:
            raise lms.ValidationError(_("Loan name required."))

        if not securities_array and type(securities_array) is not list:
            raise lms.ValidationError(_("Securities required."))

        securities_valid = True

        for i in securities_array:
            if type(i) is not dict:
                securities_valid = False
                message = _("items in securities need to be dictionaries")
                break

            keys = i.keys()
            if "isin" not in keys or "quantity" not in keys:
                securities_valid = False
                message = _("any/all of isin, quantity not present")
                break

            if type(i["isin"]) is not str or len(i["isin"]) > 12:
                securities_valid = False
                message = _("isin not correct")
                break

            if not frappe.db.exists("Allowed Security", i["isin"]):
                securities_valid = False
                message = _("{} isin not found").format(i["isin"])
                break

            valid_isin = frappe.db.sql(
                "select sum(quantity) total_pledged from `tabLoan Collateral` where request_type='Pledge' and loan={} and isin={}".format(
                    loan_name, i["isin"]
                ),
                as_dict=1,
            )
            if not valid_isin:
                securities_valid = False
                message = _("invalid isin")
                break
            elif i["quantity"] <= valid_isin[0].total_pledged:
                securities_valid = False
                message = _("invalid unpledge quantity")
                break

        if securities_valid:
            securities_list = [i["isin"] for i in securities]

            if len(set(securities_list)) != len(securities_list):
                securities_valid = False
                message = _("duplicate isin")

        if not securities_valid:
            raise lms.ValidationError(message)

        loan = frappe.get_doc("Loan", loan_name)
        if not loan:
            return lms.generateResponse(
                status=404, message=_("Loan {} does not exist.".format(loan_name))
            )

        customer = lms.get_customer(frappe.session.user)
        if loan.customer != customer.name:
            return lms.generateResponse(
                status=403, message=_("Please use your own loan.")
            )

        UNPLDGDTLS = []
        for unpledge in securities_array:
            isin_data = frappe.db.sql(
                "select isin, psn, quantity from `tabLoan Collateral` where request_type='Pledge' and loan={} and isin={} order by creation ASC".format(
                    loan_name, unpledge["isin"]
                ),
                as_dict=1,
            )
            unpledge_qty = unpledge.quantity

            for pledged_item in isin_data:
                if unpledge_qty == 0:
                    break

                removed_qty_from_current_pledge_entity = 0

                if unpledge_qty >= pledged_item.quantity:
                    removed_qty_from_current_pledge_entity = pledged_item.quantity
                else:
                    removed_qty_from_current_pledge_entity = (
                        pledged_item.quantity - unpledge_qty
                    )

                body_item = {
                    "PRNumber": pledged_item.prn,
                    "PartQuantity": removed_qty_from_current_pledge_entity,
                }
                UNPLDGDTLS.append(body_item)

                unpledge_qty -= removed_qty_from_current_pledge_entity

        las_settings = frappe.get_single("LAS Settings")
        API_URL = "{}{}".format(las_settings.cdsl_host, las_settings.unpledge_setup_uri)
        payload = {
            "URN": "URN" + lms.random_token(length=13, is_numeric=True),
            "UNPLDGDTLS": json.loads(UNPLDGDTLS),
        }

        response = requests.post(
            API_URL, headers=las_settings.cdsl_headers(), json=payload
        )

        response_json = response.json()
        frappe.logger().info(
            {
                "CDSL UNPLEDGE HEADERS": las_settings.cdsl_headers(),
                "CDSL UNPLEDGE PAYLOAD": payload,
                "CDSL UNPLEDGE RESPONSE": response_json,
            }
        )

        if response_json and response_json.get("Success") == True:
            return lms.generateResponse(message="CDSL", data=response_json)
        else:
            return lms.generateResponse(
                is_success=False, message="CDSL UnPledge Error", data=response_json
            )
    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return generateResponse(is_success=False, error=e)


@frappe.whitelist()
def create_topup_old(loan_name, file_id):
    try:
        lms.validate_http_method("POST")

        if not loan_name:
            raise lms.ValidationError(_("Loan name required."))

        loan = frappe.get_doc("Loan", loan_name)
        if not loan:
            return lms.generateResponse(
                status=404, message=_("Loan {} does not exist".format(loan_name))
            )

        customer = lms.__customer()
        if loan.customer != customer.name:
            return lms.generateResponse(
                status=403, message=_("Please use your own loan")
            )

        # check if topup available
        top_up_available = (
            loan.total_collateral_value * loan.allowable_ltv / 100
        ) > loan.sanctioned_limit
        if not top_up_available:
            raise lms.ValidationError(_("Topup not available."))

        topup_amt = (
            loan.total_collateral_value * (loan.allowable_ltv / 100)
        ) - loan.sanctioned_limit
        loan.drawing_power += topup_amt
        loan.sanctioned_limit += topup_amt
        loan.save(ignore_permissions=True)

        lms.save_signed_document(file_id, doctype="Loan", docname=loan.name)

        return lms.generateResponse(message="Topup added successfully.", data=loan)

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return generateResponse(is_success=False, error=e)


@frappe.whitelist()
def create_topup(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_name": "required",
                "topup_amount": ["required", lambda x: type(x) == float],
            },
        )

        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )
        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

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
            return utils.respondWithFailure(status=417, message="Top up not available")
        elif data.get("topup_amount") <= 0:
            return utils.respondWithFailure(
                status=417, message="Top up amount can not be 0 or less than 0"
            )
        elif data.get("topup_amount") > topup_amt:
            return utils.respondWithFailure(
                status=417,
                message="Top up amount can not be more than Rs. {}".format(topup_amt),
            )
        elif 0.0 < data.get("topup_amount") <= topup_amt:

            frappe.db.begin()
            topup_application = frappe.get_doc(
                {
                    "doctype": "Top up Application",
                    "loan": loan.name,
                    "top_up_amount": data.get("topup_amount"),
                    "sanctioned_limit": loan.sanctioned_limit,
                    "time": frappe.utils.now_datetime(),
                    "status": "Pending",
                    "customer": customer.name,
                    "customer_name": customer.full_name,
                }
            )
            topup_application.save(ignore_permissions=True)
            frappe.db.commit()

            data = {"topup_application_name": topup_application.name}

        return utils.respondWithSuccess(data=data)
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def loan_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_name": "required",
                "transactions_per_page": "",
                "transactions_start": "",
            },
        )

        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            return utils.respondNotFound(message=frappe._("Loan not found."))

        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

        if not data.get("transactions_per_page", None):
            data["transactions_per_page"] = 15
        if not data.get("transactions_start", None):
            data["transactions_start"] = 0

        loan_transactions_list = frappe.db.get_all(
            "Loan Transaction",
            filters={"loan": data.get("loan_name"), "docstatus": 1},
            order_by="time desc",
            fields=[
                "transaction_type",
                "record_type",
                "amount",
                "time",
            ],
            start=data.get("transactions_start"),
            page_length=data.get("transactions_per_page"),
        )

        if len(loan_transactions_list) > 0:
            loan_transactions_list = list(
                map(
                    lambda item: dict(
                        item, amount=lms.amount_formatter(item["amount"])
                    ),
                    loan_transactions_list,
                )
            )

        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None

        if loan_margin_shortfall:
            loan_margin_shortfall = loan_margin_shortfall.as_dict()
            if loan_margin_shortfall.status == "Request Pending":
                pledged_securities_for_mg_shortfall = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                        "status": ["not in", ["Approved", "Rejected"]],
                    },
                    fields=["*"],
                )

                # payment_for_mg_shortfall = frappe.get_all("Loan Transaction", filters={"loan_margin_shortfall": loan_margin_shortfall.name, "transaction_type": "Payment", "status": ["not in",["Approved", "Rejected"]]}, fields=["*"])

                # if pledged_securities_for_mg_shortfall:
                #     pledged_paid_shortfall = math.ceil(pledged_securities_for_mg_shortfall[0].total_collateral_value)
                #     remaining_shortfall = loan_margin_shortfall.shortfall - pledged_paid_shortfall
                # elif payment_for_mg_shortfall:
                #     cash_paid_shortfall = payment_for_mg_shortfall[0].amount
                #     remaining_shortfall = loan_margin_shortfall.minimum_cash_amount - cash_paid_shortfall

                # loan_margin_shortfall["action_taken_msg"] = """Total Margin Shortfall: Rs. {}
                #         Action Taken on: Rs. {}
                #         On {} we received a payment request of Rs. {}. The request is under process
                #         and will soon be approved by the Lender.
                #         Remaining Margin Shortfall (after the processing of the payment/pledge request)): Rs. {}""".format(loan_margin_shortfall.shortfall, loan_margin_shortfall.shortfall, (pledged_securities_for_mg_shortfall[0].creation).strftime("%d.%m.%Y %I:%M %p") if pledged_securities_for_mg_shortfall else (payment_for_mg_shortfall[0].creation).strftime("%d.%m.%Y %I:%M %p"), pledged_paid_shortfall if pledged_securities_for_mg_shortfall else cash_paid_shortfall, 0 if remaining_shortfall <= 0 else remaining_shortfall) if pledged_securities_for_mg_shortfall or payment_for_mg_shortfall else None
                # loan_margin_shortfall["deadline_in_hrs"] = None

            elif loan_margin_shortfall.status == "Pending":
                mg_shortfall_action = frappe.get_doc(
                    "Margin Shortfall Action",
                    loan_margin_shortfall.margin_shortfall_action,
                )
                hrs_difference = (
                    loan_margin_shortfall.deadline - frappe.utils.now_datetime()
                )
                if mg_shortfall_action.sell_off_after_hours:
                    date_array = set(
                        loan_margin_shortfall.creation.date() + timedelta(days=x)
                        for x in range(
                            0,
                            (
                                loan_margin_shortfall.deadline.date()
                                - loan_margin_shortfall.creation.date()
                            ).days
                            + 1,
                        )
                    )
                    holidays = date_array.intersection(set(holiday_list()))
                    hrs_difference = (
                        loan_margin_shortfall.deadline
                        - frappe.utils.now_datetime()
                        - timedelta(days=(len(holidays) if holidays else 0))
                    )

                loan_margin_shortfall["action_taken_msg"] = None
                loan_margin_shortfall["deadline_in_hrs"] = (
                    convert_sec_to_hh_mm_ss(abs(hrs_difference).total_seconds())
                    if loan_margin_shortfall.deadline > frappe.utils.now_datetime()
                    else "00:00:00"
                )

        # Interest Details
        interest_total = frappe.db.sql(
            """select sum(unpaid_interest) as total_amt from `tabLoan Transaction` where loan=%s and transaction_type in ('Interest', 'Additional Interest', 'Penal Interest') and unpaid_interest > 0""",
            loan.name,
            as_dict=1,
        )

        if interest_total[0]["total_amt"]:
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

            interest = {
                "total_interest_amt": round(interest_total[0]["total_amt"], 2),
                "due_date": due_date.strftime("%d.%m.%Y"),
                "due_date_txt": due_date_txt,
                "info_msg": info_msg,
            }
        else:
            interest = None

        existing_topup_application = frappe.get_all(
            "Top up Application",
            filters={
                "loan": loan.name,
                "customer": loan.customer,
                "status": ["not IN", ["Approved", "Rejected"]],
            },
            fields=["count(name) as in_process"],
        )
        topup = None
        if existing_topup_application[0]["in_process"] == 0:
            topup = loan.max_topup_amount()

        # Increase Loan
        existing_loan_application = frappe.get_all(
            "Loan Application",
            filters={
                "loan": loan.name,
                "customer": loan.customer,
                "status": ["not IN", ["Approved", "Rejected"]],
            },
            fields=["count(name) as in_process"],
        )

        increase_loan = None
        if existing_loan_application[0]["in_process"] == 0:
            increase_loan = 1

        res = {
            "loan": loan,
            "transactions": loan_transactions_list,
            "margin_shortfall": loan_margin_shortfall,
            "interest": interest,
            "topup": topup if topup else None,
            "increase_loan": increase_loan,
        }

        sell_collateral_application_exist = frappe.get_all(
            "Sell Collateral Application",
            filters={"loan": loan.name, "status": "Pending"},
            order_by="creation desc",
            page_length=1,
        )
        res["sell_collateral"] = 1
        if len(sell_collateral_application_exist):
            res["sell_collateral"] = None

        # check if any pending unpledge application exist
        loan_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            {"loan": loan.name, "status": "Pending"},
            page_length=1,
        )
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
def loan_withdraw_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"loan_name": "required"})

        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(
                message=_("Please use your own Loan Application.")
            )

        # set amount_available_for_withdrawal
        max_withdraw_amount = loan.maximum_withdrawable_amount()
        loan = loan.as_dict()
        loan.amount_available_for_withdrawal = max_withdraw_amount

        data = {
            "loan": loan,
        }

        # append bank list if first withdrawal transaction
        filters = {"loan": loan.name, "transaction_type": "Withdrawal", "docstatus": 1}
        if frappe.db.count("Loan Transaction", filters) == 0:
            data["banks"] = lms.__banks()

        return utils.respondWithSuccess(data=data)
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def request_loan_withdraw_otp():
    try:
        utils.validator.validate_http_method("POST")

        user = lms.__user()

        frappe.db.begin()
        lms.create_user_token(
            entity=user.username,
            token_type="Withdraw OTP",
            token=lms.random_token(length=4, is_numeric=True),
        )
        frappe.db.commit()
        return utils.respondWithSuccess(message="Withdraw OTP sent")
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def loan_withdraw_request(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_name": "required",
                "amount": ["required", lambda x: type(x) == float],
                "bank_account_name": "",
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_name") + data.get("bank_account_name")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        user = lms.__user()
        banks = lms.__banks()

        token = lms.verify_user_token(
            entity=user.username, token=data.get("otp"), token_type="Withdraw OTP"
        )

        if token.expiry <= frappe.utils.now_datetime():
            return utils.respondUnauthorized(message=frappe._("Withdraw OTP Expired."))

        lms.token_mark_as_used(token)

        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(
                message=_("Please use your own Loan Application.")
            )

        # need bank if first withdrawal transaction
        filters = {"loan": loan.name, "transaction_type": "Withdrawal", "docstatus": 1}
        if frappe.db.count("Loan Transaction", filters) == 0 and not data.get(
            "bank_account_name", None
        ):
            return utils.respondWithFailure(
                status=417, message="Need bank account for first withdrawal"
            )

        if not data.get("bank_account_name", None):
            default_bank = None
            for i in banks:
                if i.is_spark_default:
                    default_bank = i.name
                    break
            data["bank_account_name"] = default_bank

        bank_account = frappe.get_doc(
            "User Bank Account", data.get("bank_account_name")
        )
        if not bank_account:
            return utils.respondNotFound(message=frappe._("Bank Account not found."))
        if data.get("bank_account_name") not in [i.name for i in banks]:
            return utils.respondForbidden(
                message=_("Please use your own Bank Account.")
            )

        # amount validation
        amount = data.get("amount", 0)
        if amount <= 0:
            return utils.respondWithFailure(
                status=417, message="Amount should be more than 0"
            )

        max_withdraw_amount = loan.maximum_withdrawable_amount()
        if amount > max_withdraw_amount:
            return utils.respondWithFailure(
                status=417,
                message="Amount can not be more than {}".format(
                    round(max_withdraw_amount, 2)
                ),
            )

        frappe.db.begin()
        withdrawal_transaction = frappe.get_doc(
            {
                "doctype": "Loan Transaction",
                "loan": loan.name,
                "transaction_type": "Withdrawal",
                "record_type": "DR",
                "time": frappe.utils.now_datetime(),
                "amount": amount,
                "requested": amount,
                "allowable": max_withdraw_amount,
                "bank_account": data.get("bank_account_name"),
                "bank": bank_account.bank,
                "account_number": bank_account.account_number,
                "ifsc": bank_account.ifsc,
                "lender": loan.lender,
            }
        )
        withdrawal_transaction.save(ignore_permissions=True)

        bank_account.is_spark_default = 1
        bank_account.save(ignore_permissions=True)
        frappe.db.commit()

        data = {"loan_transaction_name": withdrawal_transaction.name}

        masked_bank_account_number = (
            len(bank_account.account_number[:-4]) * "x"
            + bank_account.account_number[-4:]
        )
        message = "Great! Your request for withdrawal has been successfully received. The amount shall be credited to your bank account {} within next 24 hours.".format(
            masked_bank_account_number
        )

        return utils.respondWithSuccess(message=message, data=data)
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def loan_payment(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_name": "required",
                "amount": ["required", lambda x: type(x) == float],
                "transaction_id": "required",
                "loan_margin_shortfall_name": "",
                "is_for_interest": ["between:0,1", lambda x: type(x) == int],
            },
        )
        frappe.logger().info(data.get("loan_name"))
        frappe.logger().info(data.get("amount"))
        frappe.logger().info(type(data.get("amount")))
        reg = lms.regex_special_characters(
            search=data.get("loan_name") + data.get("loan_margin_shortfall_name")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        if data.get("transaction_id"):
            # for firebase token "-_:" these characters are excluded from regex string
            reg = lms.regex_special_characters(
                search=data.get("transaction_id"),
                regex=re.compile("[@!#$%^&*()<>?/\|}{~`]"),
            )
            if reg:
                return utils.respondWithFailure(
                    status=422,
                    message=frappe._("Special Characters not allowed."),
                )

        customer = lms.__customer()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

        if data.get("loan_margin_shortfall_name", None):
            try:
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", data.get("loan_margin_shortfall_name")
                )
            except frappe.DoesNotExistError:
                return utils.respondNotFound(
                    message=_("Loan Margin Shortfall not found.")
                )
            if loan.name != loan_margin_shortfall.loan:
                return utils.respondForbidden(
                    message=_("Loan Margin Shortfall should be for the provided loan.")
                )

        frappe.db.begin()
        loan.create_loan_transaction(
            transaction_type="Payment",
            amount=data.get("amount"),
            transaction_id=data.get("transaction_id"),
            loan_margin_shortfall_name=data.get("loan_margin_shortfall_name", None),
            is_for_interest=data.get("is_for_interest", None),
        )
        frappe.db.commit()

        return utils.respondWithSuccess()
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def loan_statement(**kwargs):
    try:
        utils.validator.validate_http_method("GET")
        data = utils.validator.validate(
            kwargs,
            {
                "loan_name": "required",
                "type": "required",
                "duration": "",
                "from_date": "",
                "to_date": "",
                "file_format": "",
                "is_email": ["between:0,1", lambda x: type(x) == int],
                "is_download": ["between:0,1", lambda x: type(x) == int],
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_name") + data.get("file_format") + data.get("type")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        if isinstance(data.get("is_download"), str):
            data["is_download"] = int(data.get("is_download"))

        if isinstance(data.get("is_email"), str):
            data["is_email"] = int(data.get("is_email"))

        customer = lms.__customer()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            return utils.respondNotFound(message=frappe._("Loan not found."))

        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))
        if data.get("type") not in [
            "Account Statement",
            "Pledged Securities Transactions",
        ]:
            return utils.respondNotFound(message=_("Request Type not found."))

        filter = (
            {"loan": data.get("loan_name"), "docstatus": 1}
            if data.get("type") == "Account Statement"
            else {"loan": data.get("loan_name")}
        )

        if data.get("is_download") and data.get("is_email"):
            return utils.respondWithFailure(
                message=frappe._(
                    "Please choose one between download or email transactions at a time."
                )
            )

        elif (
            (data.get("is_download") or data.get("is_email"))
            and (data.get("from_date") or data.get("to_date"))
            and data.get("duration")
        ):
            return utils.respondWithFailure(
                message=frappe._(
                    "Please use either 'From date and To date' or Duration"
                )
            )

        elif (data.get("from_date") and not data.get("to_date")) or (
            not data.get("from_date") and data.get("to_date")
        ):
            return utils.respondWithFailure(
                message=frappe._("Please use both 'From date and To date'")
            )

        elif (data.get("is_download") or data.get("is_email")) and (
            not data.get("file_format")
            or data.get("file_format") not in ["pdf", "excel"]
        ):
            return utils.respondWithFailure(
                message=frappe._("Please select PDF/Excel file format")
            )

        if data.get("from_date") and data.get("to_date"):
            try:
                from_date = datetime.strptime(data.get("from_date"), "%d-%m-%Y")
                to_date = datetime.strptime(data.get("to_date"), "%d-%m-%Y")
            except ValueError:
                return utils.respondWithFailure(
                    status=417,
                    message=frappe._("Incorrect date format, should be DD-MM-YYYY"),
                )

            if from_date > to_date:
                return utils.respondWithFailure(
                    message=frappe._("From date cannot be greater than To date")
                )

            if data.get("type") == "Account Statement":
                filter["time"] = ["between", (from_date, to_date)]
            elif data.get("type") == "Pledged Securities Transactions":
                from_to_date = (
                    "`tabCollateral Ledger`.creation BETWEEN '{}' and '{}'".format(
                        from_date, to_date + timedelta(days=1)
                    )
                )

        elif data.get("duration"):
            if data.get("duration") not in [
                "curr_month",
                "prev_1",
                "prev_3",
                "prev_6",
                "current_year",
            ]:
                return utils.respondWithFailure(
                    message=frappe._("Please provide valid Duration")
                )

            curr_month = (
                datetime.strptime(frappe.utils.today(), "%Y-%m-%d")
                .date()
                .replace(day=1)
            )
            last_day_of_prev_month = datetime.strptime(
                frappe.utils.today(), "%Y-%m-%d"
            ).date().replace(day=1) - timedelta(days=1)

            prev_1_month = (
                curr_month - timedelta(days=last_day_of_prev_month.day)
            ).replace(day=1)
            prev_3_month = (
                curr_month - timedelta(weeks=8, days=last_day_of_prev_month.day)
            ).replace(day=1)
            prev_6_month = (
                curr_month - timedelta(weeks=20, days=last_day_of_prev_month.day)
            ).replace(day=1)
            current_year = date(
                datetime.strptime(frappe.utils.today(), "%Y-%m-%d").date().year, 4, 1
            )

            if curr_month < current_year:
                current_year = current_year - timedelta(
                    weeks=52.1775
                )  # previous financial year
            duration_date = None
            if data.get("duration") == "curr_month":
                duration_date = curr_month
            elif data.get("duration") == "prev_1":
                duration_date = prev_1_month
            elif data.get("duration") == "prev_3":
                duration_date = prev_3_month
            elif data.get("duration") == "prev_6":
                duration_date = prev_6_month
            elif data.get("duration") == "current_year":
                duration_date = current_year
            else:
                duration_date = datetime.strptime(
                    frappe.utils.today(), "%Y-%m-%d"
                ).date()

            if data.get("type") == "Account Statement":
                filter["time"] = [">=", datetime.strftime(duration_date, "%Y-%m-%d")]
            elif data.get("type") == "Pledged Securities Transactions":
                duration_date = "`tabCollateral Ledger`.creation >= '{}'".format(
                    datetime.strftime(duration_date, "%Y-%m-%d %H:%M:%S")
                )
        else:
            if data.get("is_download") or data.get("is_email"):
                return utils.respondWithFailure(
                    message=frappe._(
                        "Please use either 'From date and To date' or Duration to proceed"
                    )
                )

        res = {"loan": loan}

        lt_list = []
        if data.get("type") == "Account Statement":
            page_length = (
                15
                if not data.get("from_date")
                and not data.get("to_date")
                and not data.get("duration")
                and not data.get("is_download")
                and not data.get("is_email")
                else ""
            )
            loan_transaction_list = frappe.db.get_all(
                "Loan Transaction",
                filters=filter,
                order_by="time desc",
                fields=[
                    "name",
                    "transaction_type",
                    "record_type",
                    "amount",
                    "DATE_FORMAT(time, '%Y-%m-%d %H:%i') as time",
                    "status",
                ],
                page_length=page_length,
            )
            if len(loan_transaction_list) <= 0:
                return utils.respondNotFound(message=_("No Record Found"))

            for list in loan_transaction_list:
                list["amount"] = lms.amount_formatter(list["amount"])
                lt_list.append(list.values())
            # lt_list = [lst.values() for lst in loan_transaction_list]
            res["loan_transaction_list"] = loan_transaction_list
            df = pd.DataFrame(lt_list)
            df.columns = loan_transaction_list[0].keys()
            loan_statement_pdf_file = "{}-loan-statement.pdf".format(
                data.get("loan_name")
            )
            loan_statement_excel_file = "{}-loan-statement.xlsx".format(
                data.get("loan_name")
            )

        elif data.get("type") == "Pledged Securities Transactions":
            page_length = (
                "15"
                if not data.get("from_date")
                and not data.get("to_date")
                and not data.get("duration")
                and not data.get("is_download")
                and not data.get("is_email")
                else ""
            )
            pledged_securities_transactions = frappe.db.sql(
                """select DATE_FORMAT(`tabCollateral Ledger`.creation, '%Y-%m-%d %H:%i') as creation, `tabSecurity`.security_name, `tabCollateral Ledger`.isin, `tabCollateral Ledger`.quantity, `tabCollateral Ledger`.request_type from `tabCollateral Ledger`
            left join `tabSecurity`
            on `tabSecurity`.name = `tabCollateral Ledger`.isin
            where `tabCollateral Ledger`.loan = '{}'
            {}
            order by creation desc
            {}""".format(
                    data.get("loan_name"),
                    "and " + from_to_date
                    if data.get("from_date") and data.get("to_date")
                    else "and " + duration_date
                    if data.get("duration")
                    else "",
                    "limit " + page_length + ";" if page_length else page_length + ";",
                ),
                as_dict=1,
            )
            if not pledged_securities_transactions:
                return utils.respondNotFound(message=_("No Record Found"))
            res["pledged_securities_transactions"] = pledged_securities_transactions
            for list in pledged_securities_transactions:
                lt_list.append(list.values())
            df = pd.DataFrame(lt_list)
            df.columns = pledged_securities_transactions[0].keys()
            loan_statement_pdf_file = "{}-pledged-securities-transactions.pdf".format(
                data.get("loan_name")
            )
            loan_statement_excel_file = (
                "{}-pledged-securities-transactions.xlsx".format(data.get("loan_name"))
            )

        if data.get("is_download") or data.get("is_email"):
            df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()

            if data.get("file_format") == "pdf":
                # PDF
                loan_statement_pdf_file_path = frappe.utils.get_files_path(
                    loan_statement_pdf_file
                )

                pdf_file = open(loan_statement_pdf_file_path, "wb")
                df.index += 1
                a = df.to_html()
                a.replace("dataframe", "center")
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

            else:
                # EXCEL
                loan_statement_excel_file_path = frappe.utils.get_files_path(
                    loan_statement_excel_file
                )
                df.to_excel(loan_statement_excel_file_path, index=False)

            loan_statement_pdf_file_url = ""
            loan_statement_excel_file_url = ""
            if data.get("is_download"):
                if data.get("type") == "Account Statement":
                    loan_statement_pdf_file_url = (
                        frappe.utils.get_url(
                            "files/{}-loan-statement.pdf".format(data.get("loan_name"))
                        )
                        if data.get("file_format") == "pdf"
                        else ""
                    )
                    loan_statement_excel_file_url = (
                        frappe.utils.get_url(
                            "files/{}-loan-statement.xlsx".format(data.get("loan_name"))
                        )
                        if data.get("file_format") == "excel"
                        else ""
                    )
                else:
                    loan_statement_pdf_file_url = (
                        frappe.utils.get_url(
                            "files/{}-pledged-securities-transactions.pdf".format(
                                data.get("loan_name")
                            )
                        )
                        if data.get("file_format") == "pdf"
                        else ""
                    )
                    loan_statement_excel_file_url = (
                        frappe.utils.get_url(
                            "files/{}-pledged-securities-transactions.xlsx".format(
                                data.get("loan_name")
                            )
                        )
                        if data.get("file_format") == "excel"
                        else ""
                    )
                res["pdf_file_url"] = loan_statement_pdf_file_url
                res["excel_file_url"] = loan_statement_excel_file_url

            elif data.get("is_email"):
                attachments = []
                if data.get("file_format") == "pdf":
                    attachments = [{"fname": loan_statement_pdf_file, "fcontent": pdf}]
                else:
                    attachments = [
                        {
                            "fname": loan_statement_excel_file,
                            "fcontent": df.to_csv(index=False),
                        },
                    ]

                res["is_mail_sent"] = 1
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject="Pledged Securities Transactions for {}".format(loan.name)
                    if data.get("type") == "Pledged Securities Transactions"
                    else "Loan A/c Statement for {}".format(loan.name),
                    message="Please see Attachments",
                    attachments=attachments,
                )

        return utils.respondWithSuccess(data=res)
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def request_unpledge_otp():
    try:
        utils.validator.validate_http_method("POST")

        # user = lms.__user()
        user_kyc = lms.__user_kyc()

        frappe.db.begin()
        lms.create_user_token(
            entity=user_kyc.mobile_number,
            token_type="Unpledge OTP",
            token=lms.random_token(length=4, is_numeric=True),
        )
        frappe.db.commit()
        return utils.respondWithSuccess(message="Unpledge OTP sent")
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def loan_unpledge_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"loan_name": "required"})

        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

        res = {"loan": loan}

        loan_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            {"loan": loan.name, "status": "Pending"},
            page_length=1,
        )
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
        # data = {"loan": loan, "unpledge": unpledge}

        return utils.respondWithSuccess(data=res)
    except utils.APIException as e:
        return e.respond()


def validate_securities_for_unpledge(securities, loan):
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
                loan.lender, lms.convert_list_to_tuple_string(securities_list)
            )
        )
        securities_list_from_db = [i[0] for i in securities_list_from_db_]

        diff = list(set(securities_list) - set(securities_list_from_db))
        if diff:
            securities_valid = False
            message = frappe._("{} isin not found".format(",".join(diff)))

    if securities_valid:
        securities_list_from_db_ = frappe.db.sql(
            "select isin, pledged_quantity from `tabLoan Item` where  parent = '{}' and isin in {}".format(
                loan.name, lms.convert_list_to_tuple_string(securities_list)
            )
        )
        securities_list_from_db = [i[0] for i in securities_list_from_db_]

        diff = list(set(securities_list) - set(securities_list_from_db))
        if diff:
            securities_valid = False
            message = frappe._("{} isin not found".format(",".join(diff)))
        else:
            securities_obj = {}
            for i in securities_list_from_db_:
                securities_obj[i[0]] = i[1]

            for i in securities:
                if i["quantity"] > securities_obj[i["isin"]]:
                    securities_valid = False
                    message = frappe._(
                        "Unpledge quantity for isin {} should not be greater than {}".format(
                            i["isin"], int(securities_obj[i["isin"]])
                        )
                    )
                    break

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
def loan_unpledge_request(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_name": "required",
                "securities": "",
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))
        loan_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            {"loan": loan.name, "status": "Pending"},
            page_length=1,
        )
        if loan_margin_shortfall:
            return utils.respondWithFailure(
                status=417,
                message="""OOPS! Dear {}, It seems you have a margin shortfall. You cannot unpledge any of the pledged securities until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                    loan.get_customer().first_name
                ),
            )

        unpledge_application_exist = frappe.get_all(
            "Unpledge Application",
            filters={"loan": loan.name, "status": "Pending"},
            order_by="creation desc",
            page_length=1,
        )
        if len(unpledge_application_exist):
            return utils.respondWithFailure(
                status=417,
                message="Unpledge Application for {} is already in process.".format(
                    loan.name
                ),
            )

        securities = validate_securities_for_unpledge(data.get("securities", {}), loan)

        user_kyc = lms.__user_kyc()
        token = lms.verify_user_token(
            entity=user_kyc.mobile_number,
            token=data.get("otp"),
            token_type="Unpledge OTP",
        )

        if token.expiry <= frappe.utils.now_datetime():
            return utils.respondUnauthorized(message=frappe._("Pledge OTP Expired."))

        frappe.db.begin()

        lms.token_mark_as_used(token)

        items = []
        for i in securities:
            temp = frappe.get_doc(
                {
                    "doctype": "Unpledge Application Item",
                    "isin": i["isin"],
                    "quantity": i["quantity"],
                }
            )
            items.append(temp)

        unpledge_application = frappe.get_doc(
            {
                "doctype": "Unpledge Application",
                "loan": data.get("loan_name"),
                "items": items,
            }
        )
        unpledge_application.insert(ignore_permissions=True)

        return utils.respondWithSuccess(data=unpledge_application)
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def request_sell_collateral_otp():
    try:
        utils.validator.validate_http_method("POST")

        user = lms.__user()

        frappe.db.begin()
        lms.create_user_token(
            entity=user.username,
            token_type="Sell Collateral OTP",
            token=lms.random_token(length=4, is_numeric=True),
        )
        frappe.db.commit()
        return utils.respondWithSuccess(message="Sell Collateral OTP sent")
    except utils.APIException as e:
        return e.respond()


@frappe.whitelist()
def sell_collateral_request(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_name": "required",
                "securities": "",
                "loan_margin_shortfall_name": "",
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_name") + data.get("loan_margin_shortfall_name")
        )
        if reg:
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Special Characters not allowed."),
            )

        user = lms.__user()
        customer = lms.__customer()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

        sell_application_exist = frappe.get_all(
            "Sell Collateral Application",
            filters={"loan": loan.name, "status": "Pending"},
            order_by="creation desc",
            page_length=1,
        )
        if len(sell_application_exist):
            return utils.respondWithFailure(
                status=417,
                message="Sell Collateral Application for {} is already in process.".format(
                    loan.name
                ),
            )

        securities = validate_securities_for_sell_collateral(
            data.get("securities", {}), data.get("loan_name")
        )

        token = lms.verify_user_token(
            entity=user.username,
            token=data.get("otp"),
            token_type="Sell Collateral OTP",
        )

        if token.expiry <= frappe.utils.now_datetime():
            return utils.respondUnauthorized(
                message=frappe._("Sell Collateral OTP Expired.")
            )

        frappe.db.begin()

        items = []
        for i in securities:
            temp = frappe.get_doc(
                {
                    "doctype": "Sell Collateral Application Item",
                    "isin": i["isin"],
                    "quantity": i["quantity"],
                }
            )
            items.append(temp)

        sell_collateral_application = frappe.get_doc(
            {
                "doctype": "Sell Collateral Application",
                "loan": data.get("loan_name"),
                "items": items,
            }
        )

        if data.get("loan_margin_shortfall_name"):
            sell_collateral_application.loan_margin_shortfall = data.get(
                "loan_margin_shortfall_name"
            )

        sell_collateral_application.insert(ignore_permissions=True)

        lms.token_mark_as_used(token)

        frappe.db.commit()

        return utils.respondWithSuccess(data=sell_collateral_application)
    except utils.APIException as e:
        return e.respond()


def validate_securities_for_sell_collateral(securities, loan_name):
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
            "select isin from `tabLoan Item` where parent = '{}' and isin in {}".format(
                loan_name, lms.convert_list_to_tuple_string(securities_list)
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
