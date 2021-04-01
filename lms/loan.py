import json
from datetime import date, datetime, timedelta

import frappe
import pandas as pd
import requests
import utils
from frappe import _
from utils.responder import respondWithFailure, respondWithSuccess

import lms


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
            frappe.db.begin()
            for tnc in frappe.get_list(
                "Terms and Conditions", filters={"is_active": 1}
            ):
                approved_tnc = frappe.get_doc(
                    {
                        "doctype": "Approved Terms and Conditions",
                        "mobile": customer.phone,
                        "tnc": tnc.name,
                        "time": datetime.now(),
                    }
                )
                approved_tnc.insert(ignore_permissions=True)
            frappe.db.commit()
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
        customer = lms.get_customer(frappe.session.user)
        loans = frappe.db.sql(
            """select
			loan.total_collateral_value, loan.name, loan.sanctioned_limit, loan.drawing_power,

			if (loan.total_collateral_value * loan.allowable_ltv / 100 > loan.sanctioned_limit, 1, 0) as top_up_available,

			if (loan.total_collateral_value * loan.allowable_ltv / 100 > loan.sanctioned_limit,
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
def create_unpledge(loan_name, securities_array):
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

        customer = lms.get_customer(frappe.session.user)
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
        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

        topup_amt = loan.max_topup_amount()
        las_settings = frappe.get_single("LAS Settings")

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
        elif (
            data.get("topup_amount") < las_settings.minimum_top_up_amount
            or data.get("topup_amount") <= 0
        ):
            return utils.respondWithFailure(
                status=417,
                message="Top up amount can not be less than Rs. {}".format(
                    las_settings.minimum_top_up_amount
                ),
            )
        elif data.get("topup_amount") > topup_amt:
            return utils.respondWithFailure(
                status=417,
                message="Top up amount can not be more than Rs. {}".format(topup_amt),
            )
        elif (
            las_settings.minimum_top_up_amount <= data.get("topup_amount") <= topup_amt
        ):

            frappe.db.begin()
            topup_application = frappe.get_doc(
                {
                    "doctype": "Top up Application",
                    "loan": data.get("loan_name"),
                    "top_up_amount": data.get("topup_amount"),
                    "time": datetime.now(),
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

        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
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
            fields=["transaction_type", "record_type", "amount", "time"],
            start=data.get("transactions_start"),
            page_length=data.get("transactions_per_page"),
        )

        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None

        # Interest Details
        interest_total = frappe.db.sql(
            """select sum(unpaid_interest) as total_amt from `tabLoan Transaction` where loan=%s and transaction_type in ('Interest', 'Additional Interest', 'Penal Interest') and unpaid_interest > 0""",
            loan.name,
            as_dict=1,
        )

        if interest_total[0]["total_amt"]:
            current_date = datetime.now()
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
                "due_date": due_date,
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
        las_settings = frappe.get_single("LAS Settings")
        topup = None
        if existing_topup_application[0]["in_process"] == 0:
            topup = loan.max_topup_amount()

            if topup:
                topup = lms.round_down_amount_to_nearest_thousand(topup)
                topup = {
                    "minimum_top_up_amount": las_settings.minimum_top_up_amount,
                    "top_up_amount": topup,
                }
            else:
                topup = None
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
            "topup": topup,
            "increase_loan": increase_loan,
        }

        return utils.respondWithSuccess(data=res)
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def loan_withdraw_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"loan_name": "required"})

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

        customer = lms.__customer()
        user = lms.__user()
        # user_kyc = lms.__user_kyc()
        banks = lms.__banks()

        token = lms.verify_user_token(
            entity=user.username, token=data.get("otp"), token_type="Withdraw OTP"
        )

        if token.expiry <= datetime.now():
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
                message="Amount can not be more than {}".format(max_withdraw_amount),
            )

        frappe.db.begin()
        withdrawal_transaction = frappe.get_doc(
            {
                "doctype": "Loan Transaction",
                "loan": loan.name,
                "transaction_type": "Withdrawal",
                "record_type": "DR",
                "time": datetime.now(),
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
                "is_for_interest": "",
            },
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
                "is_email": "",
                "is_download": "",
            },
        )

        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))
        if data.get("type") not in [
            "Account Statement",
            "Pledged Securities Transactions",
        ]:
            return utils.respondNotFound(message=_("Request Type not found."))

        filter = (
            {"parent": data.get("loan_name")}
            if data.get("type") == "Pledged Securities Transactions"
            else {"loan": data.get("loan_name")}
        )

        if (
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
        
        # elif data.get("is_download") and data.get("is_email"):
        #     return utils.respondWithFailure(
        #         message=frappe._(
        #             "Please choose one between download or email transactions at a time."
        #         )
        #     )

        if data.get("from_date") and data.get("to_date"):
            from_date = datetime.strptime(data.get("from_date"), "%d-%m-%Y")
            to_date = datetime.strptime(data.get("to_date"), "%d-%m-%Y")

            if from_date > to_date:
                return utils.respondWithFailure(
                    message=frappe._("From date cannot be greater than To date")
                )

            if data.get("type") == "Account Statement":
                filter["time"] = ["between", (from_date, to_date)]
            elif data.get("type") == "Pledged Securities Transactions":
                filter["creation"] = ["between", (from_date, to_date)]

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

            curr_month = date.today().replace(day=1)
            last_day_of_prev_month = date.today().replace(day=1) - timedelta(days=1)

            prev_1_month = (
                curr_month - timedelta(days=last_day_of_prev_month.day)
            ).replace(day=1)
            prev_3_month = (
                curr_month - timedelta(weeks=8, days=last_day_of_prev_month.day)
            ).replace(day=1)
            prev_6_month = (
                curr_month - timedelta(weeks=20, days=last_day_of_prev_month.day)
            ).replace(day=1)
            current_year = date(date.today().year, 4, 1)

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
                duration_date = date.today()

            if data.get("type") == "Account Statement":
                filter["time"] = [">=", datetime.strftime(duration_date, "%Y-%m-%d")]
            elif data.get("type") == "Pledged Securities Transactions":
                filter["creation"] = [
                    ">=",
                    datetime.strftime(duration_date, "%Y-%m-%d"),
                ]
        else:
            if data.get("is_download") or data.get("is_email"):
                return utils.respondWithFailure(
                    message=frappe._(
                        "Please use either 'From date and To date' or Duration to proceed"
                    )
                )

        page_length = (
            15
            if not data.get("from_date")
            and not data.get("to_date")
            and not data.get("duration")
            and not data.get("is_download")
            and not data.get("is_email")
            else ""
        )

        res = {"loan": loan}
        # if not data.get("from_date") and not data.get("to_date") and not data.get("duration"):
        #     filter = {"loan": data.get("loan_name")}

        lt_list = []
        if data.get("type") == "Account Statement":
            loan_transaction_list = frappe.db.get_all(
                "Loan Transaction",
                filters=filter,
                order_by="time desc",
                fields=[
                    "name",
                    "transaction_type",
                    "record_type",
                    "round(amount, 2) as amount",
                    "DATE_FORMAT(time, '%Y-%m-%d %H:%i') as time",
                    "status",
                ],
                page_length=page_length,
            )
            if not loan_transaction_list:
                return utils.respondNotFound(message=_("No Record Found"))
            res["loan_transaction_list"] = loan_transaction_list
            for list in loan_transaction_list:
                lt_list.append(list.values())
            df = pd.DataFrame(lt_list)
            df.columns = loan_transaction_list[0].keys()
            loan_statement_pdf_file = "{}-loan-statement.pdf".format(
                data.get("loan_name")
            )
            loan_statement_excel_file = "{}-loan-statement.xlsx".format(
                data.get("loan_name")
            )

        elif data.get("type") == "Pledged Securities Transactions":
            pledged_securities_transactions = frappe.get_all(
                "Loan Item",
                filters=filter,
                order_by="creation desc",
                fields=[
                    "pledged_quantity",
                    "security_name",
                    "isin",
                    "security_category",
                    "price",
                    "amount",
                ],
                page_length=page_length,
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
            # loan_statement_dir_path = frappe.utils.get_files_path("loan")
            # import os

            # if not os.path.exists(loan_statement_dir_path):
            #     os.mkdir(loan_statement_dir_path)

            df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()

            if data.get("file_format") == "pdf":
                # PDF
                loan_statement_pdf_file_path = frappe.utils.get_files_path(
                    loan_statement_pdf_file
                )

                pdf_file = open(loan_statement_pdf_file_path, "wb")
                # pdf_file = open(loan_statement_pdf_file_path, "w")
                df.index += 1
                a = df.to_html()
                style = """<style>
                tr {
                page-break-inside: avoid;
                }
                </style>
                """

                html_with_style = style + a

                from frappe.utils.pdf import get_pdf

                # pdf = get_pdf(a)
                pdf = get_pdf(html_with_style)
                pdf_file.write(pdf)
                # pdf_file.write(a)
                pdf_file.close()

                # loan_statement_pdf_file = frappe.get_doc(
                #     {
                #         "doctype": "File",
                #         "file_name": loan_statement_pdf_file,
                #         "content": pdf,
                #         "folder": "Home",
                #     }
                # )
                # loan_statement_pdf_file.save(ignore_permissions=True)
            else:
                # EXCEL
                loan_statement_excel_file_path = frappe.utils.get_files_path(
                    loan_statement_excel_file
                )
                df.to_excel(loan_statement_excel_file_path, index=False)

                # loan_statement_excel_file = frappe.get_doc(
                #     {
                #         "doctype": "File",
                #         "file_name": loan_statement_excel_file,
                #         "content": df.to_csv(index=False),
                #         "folder": "Home",
                #     }
                # )
                # loan_statement_excel_file.save(ignore_permissions=True)

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
                    #     pdf_file = frappe.get_doc(
                    #         "File", {"file_name": loan_statement_pdf_file.file_name}
                    #     )
                    #     pdf_content = pdf_file.get_content()
                    attachments = [{"fname": loan_statement_pdf_file, "fcontent": pdf}]
                else:
                    # excel_file = frappe.get_doc(
                    #     "File", {"file_name": loan_statement_excel_file.file_name}
                    # )
                    # excel_content = excel_file.get_content()
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
