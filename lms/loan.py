import json
import math
import re
from datetime import date, datetime, timedelta

import frappe
import pandas as pd
import requests
import utils
from bs4 import BeautifulSoup
from frappe import _
from lxml import etree
from utils.responder import respondWithFailure, respondWithSuccess

import lms
from lms import convert_sec_to_hh_mm_ss, holiday_list
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.approved_terms_and_conditions.approved_terms_and_conditions import (
    ApprovedTermsandConditions,
)


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
                raise utils.exceptions.APIException(res.text)

            data = res.json()

            esign_url_dict = esign_request.get("esign_url_dict")
            esign_url_dict["id"] = data.get("id")
            url = esign_request.get("esign_url").format(**esign_url_dict)

            return utils.respondWithSuccess(
                message=_("Esign URL."),
                data={"esign_url": url, "file_id": data.get("id")},
            )
        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))
    except utils.exceptions.APIException as e:
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
                raise utils.exceptions.APIException(res.text)

            data = res.json()

            esign_url_dict = esign_request.get("esign_url_dict")
            esign_url_dict["id"] = data.get("id")
            url = esign_request.get("esign_url").format(**esign_url_dict)

            return utils.respondWithSuccess(
                message=_("Esign URL."),
                data={"esign_url": url, "file_id": data.get("id")},
            )
        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))
    except utils.exceptions.APIException as e:
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
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                frappe.enqueue_doc(
                    "Notification",
                    "Loan Application Esign Done",
                    method="send",
                    doc=doc,
                )
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
                msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of your new OD limit. Thank you for your patience. - Spark Loans"
                receiver_list = list(
                    set([str(customer.phone), str(customer.get_kyc().mobile_number)])
                )
                from frappe.core.doctype.sms_settings.sms_settings import send_sms

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Topup E-signing was successful",
                    fields=["*"],
                )
                lms.send_spark_push_notification(
                    fcm_notification=fcm_notification, customer=customer
                )

            return utils.respondWithSuccess()
        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))
    except utils.exceptions.APIException as e:
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
        data["user_can_pledge"] = 0
        if not loans:
            under_process_la = frappe.get_all(
                "Loan Application",
                {
                    "customer": customer.name,
                    "status": ["not IN", ["Rejected", "Pledge Failure"]],
                    "pledge_status": ["!=", "Failure"],
                },
            )
            if not under_process_la:
                data["user_can_pledge"] = 1

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
        user_kyc = lms.__user_kyc()
        user = lms.__user()

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
            current = frappe.utils.now_datetime()
            expiry = frappe.utils.add_years(current, 1) - timedelta(days=1)

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
                    "expiry_date": expiry,
                    "lender": loan.lender,
                }
            )
            topup_application.save(ignore_permissions=True)
            frappe.db.commit()

            for tnc in frappe.get_list(
                "Terms and Conditions", filters={"is_active": 1}
            ):
                # if data.get("loan_name"):
                top_up_approved_tnc = {
                    "doctype": "Top up Application",
                    "docname": topup_application.name,
                    "mobile": user.username,
                    "tnc": tnc.name,
                    "time": frappe.utils.now_datetime(),
                }
                ApprovedTermsandConditions.create_entry(**top_up_approved_tnc)
                frappe.db.commit()

            # loan = frappe.get_doc("Loan", topup_application.loan)
            # lender = frappe.get_doc("Lender", loan.lender)
            frappe.enqueue_doc(
                "Notification", "Top up Request", method="send", doc=user_kyc
            )

            msg = "Dear Customer,\nYour top up request has been successfully received and is under process. We shall reach out to you very soon. Thank you for your patience -Spark Loans"
            receiver_list = list(
                set([str(customer.phone), str(customer.get_kyc().mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

            # tnc_ul = ["<ul>"]
            # tnc_ul.append(
            #     "<li><strong> Name Of Borrower : {} </strong>".format(
            #         user_kyc.investor_name
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Address Of Borrower </strong> : {}".format(
            #         user_kyc.address or ""
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Nature of facility sanctioned : Loan Against Securities - Overdraft facility;</strong></li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Purpose </strong>: General Purpose. The facility shall not be used for anti-social or illegal purposes;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Top up Amount </strong>: <strong>Rs. {}</strong> (Rounded to nearest 1000, lower side) (Final limit will be based on the Quantity and Value of pledged securities at the time of acceptance of pledge. The limit is subject to change based on the pledged shares from time to time as also the value thereof determined by our management as per our internal parameters from time to time);".format(
            #         topup_application.top_up_amount + loan.drawing_power
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append("<li><strong> Interest type </strong>: Floating</li>")
            # tnc_ul.append(
            #     "<li><strong> Rate of Interest </strong>: <strong>{}%  per month</strong> after rebate, if paid within <strong>7 days</strong> of due date. Otherwise Rebate of <strong>0.20%</strong> will not be applicable and higher interest rate will be applicable [Interest rate is subject to change based on management discretion from time to time];".format(
            #         lender.rate_of_interest
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Details of security / Collateral obtained </strong>: Shares and other securities as will be pledged from time to time to maintain the required security coverage;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Security Coverage </strong>: Shares & Equity oriented Mutual Funds - <strong>Minimum 200%</strong>, Other Securities - As per rules applicable from time to time;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Facility Tenure </strong>: <strong>12 Months</strong> (Renewable at Lender’s discretion, as detailed in the T&C);</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Repayment Through </strong>: Cash Flows /Sale of Securities/Other Investments Maturing;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Mode of communication</strong> of changes in interest rates and others : Website and Mobile App notification, SMS, Email, Letters, Notices at branches, communication through statement of accounts of the borrower, or any other mode of communication;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> EMI Payable </strong>: <strong>Not Applicable;</strong></li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Penal Interest rate / Penal Charges </strong>: In case of occurrence of Event of Default (EOD), Penal Interest shall be charged <strong>upto 4.00% per month</strong> over and above applicable Interest Rate;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Processing Fee </strong>: <strong>{}%</strong> of the sanctioned amount, subject to minimum amount of <strong>Rs. 1500/-;</strong>".format(
            #         lender.lender_processing_fees
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Account Renewal charges </strong>: <strong>{}%</strong> of the renewal amount (Facility valid for a period of 12 months from the date of sanction; account renewal charges shall be debited at the end of 12 months), subject to minimum amount of <strong>Rs. 750/-;</strong>".format(
            #         lender.account_renewal_charges
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Documentation charges </strong>: <strong>Rs. {}/-;</strong>".format(
            #         lender.documentation_charges
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Stamp duty & other statutory charges </strong>: At actuals;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Pre-payment charges </strong>: <strong>NIL;</strong></li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Transaction Charges per Request (per variation in the composition of the Demat securities pledged) </strong>: <strong>Upto Rs. {}/-</strong> per request;".format(
            #         lender.transaction_charges_per_request
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Collection Charges on Sale of security in the event of default or otherwise </strong>: <strong>{}%</strong> of the sale amount plus all brokerage, incidental transaction charges, costs and expenses and other levies as per actuals;".format(
            #         lender.security_selling_share
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Credit Information Companies'(CICs) Charges </strong>: <strong>Upto Rs {}/-</strong> per instance (For individuals);".format(
            #         lender.cic_charges
            #     )
            #     + "</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Solvency Certificate </strong>: Not Applicable;</li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> No Due Certificate / No Objection Certificate (NOC) </strong>: <strong>NIL;</strong></li>"
            # )
            # tnc_ul.append(
            #     "<li><strong> Legal & incidental charges </strong>: As per actuals;</li></ul>"
            # )
            # topup_application.create_tnc_file()
            # tnc_file_url = frappe.utils.get_url(
            #     "files/tnc/{}.pdf".format(topup_application.name)
            # )
            # tnc_header = "Please refer to the <a href='{}'>Terms & Conditions</a> for LAS facility, for detailed terms.".format(
            #     tnc_file_url
            # )
            # tnc_footer = "You shall be required to authenticate (in token of you having fully read and irrevocably and unconditionally accepted and authenticated) the above application for loan including the pledge request and the Terms and Conditions (which can be opened by clicking on the links) and entire contents thereof, by entering the OTP that will be sent to you next on your registered mobile number with CDSL."
            # tnc_checkboxes = [
            #     i.tnc
            #     for i in frappe.get_all(
            #         "Terms and Conditions",
            #         filters={"is_active": 1},
            #         fields=["tnc"],
            #         order_by="creation asc",
            #     )
            # ]

            data = {
                "topup_application_name": topup_application.name,
                #     "tnc_file": tnc_file_url,
                #     "tnc_html": "".join(tnc_ul),
                #     "tnc_header": tnc_header,
                #     "tnc_footer": tnc_footer,
                #     "tnc_checkboxes": tnc_checkboxes,
            }

            # for tnc in frappe.get_list(
            #     "Terms and Conditions", filters={"is_active": 1}
            # ):
            #     top_up_approved_tnc = {
            #         "doctype": "Top up Application",
            #         "docname": topup_application.name,
            #         "mobile": user.username,
            #         "tnc": tnc.name,
            #         "time": frappe.utils.now_datetime(),
            #     }
            #     ApprovedTermsandConditions.create_entry(**top_up_approved_tnc)
            #     frappe.db.commit()

        return utils.respondWithSuccess(data=data)
    except utils.exceptions.APIException as e:
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
                        item,
                        amount=frappe.utils.fmt_money(item["amount"])
                        # item, amount=lms.amount_formatter(item["amount"])
                    ),
                    loan_transactions_list,
                )
            )

        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None

        payment_in_process = 0
        if loan_margin_shortfall:
            loan_margin_shortfall = loan_margin_shortfall.as_dict()
            # loan_margin_shortfall = loan_margin_shortfall[0]
            loan_margin_shortfall["action_taken_msg"] = None
            loan_margin_shortfall["linked_application"] = None
            loan_margin_shortfall["deadline_in_hrs"] = None
            loan_margin_shortfall["shortfall_c_str"] = lms.amount_formatter(
                loan_margin_shortfall.shortfall_c
            )
            loan_margin_shortfall["is_today_holiday"] = 0

            if loan_margin_shortfall.status == "Request Pending":
                pledged_paid_shortfall = 0
                sell_off_shortfall = 0
                cash_paid_shortfall = 0
                pledged_securities_for_mg_shortfall = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                        "status": ["not in", ["Approved", "Rejected"]],
                    },
                    fields=["*"],
                )

                payment_for_mg_shortfall = frappe.get_all(
                    "Loan Transaction",
                    filters={
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                        "transaction_type": "Payment",
                        "status": ["not in", ["Approved", "Rejected"]],
                        "razorpay_event": [
                            "not in",
                            ["", "Failed", "Payment Cancelled"],
                        ],
                    },
                    fields=["*"],
                )

                sell_collateral_for_mg_shortfall = frappe.get_all(
                    "Sell Collateral Application",
                    filters={
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                        "status": ["not in", ["Approved", "Rejected"]],
                    },
                    fields=["*"],
                )

                if (
                    pledged_securities_for_mg_shortfall
                    or payment_for_mg_shortfall
                    or sell_collateral_for_mg_shortfall
                ):
                    loan_margin_shortfall[
                        "action_taken_msg"
                    ] = "Total Margin Shortfall: Rs. {}/- ".format(
                        loan_margin_shortfall.shortfall
                    )

                if pledged_securities_for_mg_shortfall:
                    pledged_paid_shortfall = math.ceil(
                        pledged_securities_for_mg_shortfall[0].total_collateral_value
                    )

                    action_taken_for_pledge = """\nOn {} we received a pledge request of Rs. {}/- which is under process. \n(Click here to see pledge summary)""".format(
                        (pledged_securities_for_mg_shortfall[0].creation).strftime(
                            "%d.%m.%Y %I:%M %p"
                        ),
                        pledged_paid_shortfall,
                    )
                    loan_margin_shortfall["action_taken_msg"] += action_taken_for_pledge

                if payment_for_mg_shortfall:
                    cash_paid_shortfall = payment_for_mg_shortfall[0].amount

                    action_taken_for_payment = """\nOn {} we received a payment of Rs. {}/- which is under process. """.format(
                        (payment_for_mg_shortfall[0].creation).strftime(
                            "%d.%m.%Y %I:%M %p"
                        ),
                        cash_paid_shortfall,
                    )
                    loan_margin_shortfall[
                        "action_taken_msg"
                    ] += action_taken_for_payment

                if sell_collateral_for_mg_shortfall:
                    sell_off_shortfall = sell_collateral_for_mg_shortfall[
                        0
                    ].total_collateral_value

                    action_taken_for_sell = """\nOn {} we received a sell collateral request of Rs. {}/- which is under process. \n(Click here to see sell collateral summary) """.format(
                        (sell_collateral_for_mg_shortfall[0].creation).strftime(
                            "%d.%m.%Y %I:%M %p"
                        ),
                        sell_off_shortfall,
                    )
                    loan_margin_shortfall["action_taken_msg"] += action_taken_for_sell

                remaining_shortfall = (
                    loan_margin_shortfall.shortfall
                    - pledged_paid_shortfall
                    - sell_off_shortfall
                    - (
                        cash_paid_shortfall
                        * (100 / loan_margin_shortfall.allowable_ltv)
                    )
                )

                if (
                    pledged_securities_for_mg_shortfall
                    or payment_for_mg_shortfall
                    or sell_collateral_for_mg_shortfall
                ):
                    loan_margin_shortfall[
                        "action_taken_msg"
                    ] += "\nRemaining Margin Shortfall (after successful processing of your action): Rs. {}/-".format(
                        round(remaining_shortfall, 2) if remaining_shortfall > 0 else 0
                    )

                loan_margin_shortfall["linked_application"] = {
                    "loan_application": frappe.get_doc(
                        "Loan Application", pledged_securities_for_mg_shortfall[0].name
                    )
                    if pledged_securities_for_mg_shortfall
                    else None,
                    "sell_collateral_application": frappe.get_doc(
                        "Sell Collateral Application",
                        sell_collateral_for_mg_shortfall[0].name,
                    )
                    if sell_collateral_for_mg_shortfall
                    else None,
                }

            if loan_margin_shortfall.status in [
                "Pending",
                "Request Pending",
                "Sell Triggered",
            ]:
                mg_shortfall_action = frappe.get_doc(
                    "Margin Shortfall Action",
                    loan_margin_shortfall.margin_shortfall_action,
                )
                hrs_difference = (
                    loan_margin_shortfall.deadline - frappe.utils.now_datetime()
                )
                # if mg_shortfall_action.sell_off_after_hours:
                # if mg_shortfall_action.sell_off_after_hours or (
                #     mg_shortfall_action.sell_off_deadline_eod
                #     and loan_margin_shortfall.creation.date()
                #     in holiday_list(is_bank_holiday=1)
                # ):
                if (
                    loan_margin_shortfall.creation.date()
                    != loan_margin_shortfall.deadline.date()
                ):
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
                    holidays = date_array.intersection(
                        set(holiday_list(is_bank_holiday=1))
                    )

                    previous_holidays = 0
                    for days in list(holidays):
                        if (
                            days >= loan_margin_shortfall.creation.date()
                            and days < frappe.utils.now_datetime().date()
                        ):
                            previous_holidays += 1

                    hrs_difference = (
                        loan_margin_shortfall.deadline
                        - frappe.utils.now_datetime()
                        - timedelta(days=(len(holidays) if holidays else 0))
                        + timedelta(
                            days=previous_holidays
                        )  # if_prev_days_in_holidays then add those days in timer
                    )

                    # if (
                    #     loan_margin_shortfall.creation.date()
                    #     < frappe.utils.now_datetime().date()
                    #     and loan_margin_shortfall.creation.date() in holidays
                    # ):
                    #     hrs_difference += (
                    #         loan_margin_shortfall.creation.replace(
                    #             hour=23, minute=59, second=59, microsecond=999999
                    #         )
                    #         - loan_margin_shortfall.creation
                    #     )

                    if frappe.utils.now_datetime().date() in holidays:
                        # if_today_holiday then add those hours in timer
                        # if (
                        #     frappe.utils.now_datetime().date()
                        #     == loan_margin_shortfall.creation.date()
                        # ):
                        #     if mg_shortfall_action.sell_off_after_hours:
                        #         start_time = datetime.strptime(
                        #             list(holidays)[-1].strftime("%Y-%m-%d %H:%M:%S.%f"),
                        #             "%Y-%m-%d %H:%M:%S.%f",
                        #         ).replace(hour=0, minute=0, second=0, microsecond=0)
                        #         print(start_time,"start_time")

                        #     else:
                        #         start_time = frappe.utils.now_datetime().replace(
                        #             hour=0, minute=0, second=0, microsecond=0
                        #         )

                        # else:
                        #     pass
                        start_time = frappe.utils.now_datetime().replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        loan_margin_shortfall["is_today_holiday"] = 1

                        hrs_difference += frappe.utils.now_datetime() - start_time

                loan_margin_shortfall["deadline_in_hrs"] = (
                    convert_sec_to_hh_mm_ss(abs(hrs_difference).total_seconds())
                    if loan_margin_shortfall.deadline > frappe.utils.now_datetime()
                    else "00:00:00"
                )

            pending_loan_transaction = frappe.get_all(
                "Loan Transaction",
                filters={
                    "loan": loan.name,
                    "status": ["=", "Pending"],
                    "razorpay_event": ["not in", ["", "Failed", "Payment Cancelled"]],
                    "loan_margin_shortfall": loan_margin_shortfall.name,
                },
            )
            if pending_loan_transaction:
                payment_in_process = 1

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
                "status": ["not IN", ["Approved", "Rejected", "Pledge Failure"]],
            },
            fields=["count(name) as in_process"],
        )

        increase_loan = None
        if existing_loan_application[0]["in_process"] == 0:
            increase_loan = 1

        res = {
            "loan": loan,
            "instrument_type": loan.instrument_type,
            "transactions": loan_transactions_list,
            "margin_shortfall": loan_margin_shortfall,
            "payment_already_in_process": payment_in_process,
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
        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None

        res["is_sell_triggered"] = 0
        if loan_margin_shortfall:
            if loan_margin_shortfall.status == "Sell Triggered":
                res["is_sell_triggered"] = 1

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

        res["amount_available_for_withdrawal"] = loan.maximum_withdrawable_amount()

        # Pledgor boid of particular loan
        res["pledgor_boid"] = frappe.db.get_value(
            "Collateral Ledger", {"loan": loan.name}, "pledgor_boid"
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
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def request_loan_withdraw_otp():
    try:
        utils.validator.validate_http_method("POST")

        user = lms.__user()
        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        if not is_dummy_account:
            frappe.db.begin()
            lms.create_user_token(
                entity=user.username,
                token_type="Withdraw OTP",
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="Withdraw OTP sent")
    except utils.exceptions.APIException as e:
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

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        if not is_dummy_account:
            token = lms.verify_user_token(
                entity=user.username, token=data.get("otp"), token_type="Withdraw OTP"
            )

            if token.expiry <= frappe.utils.now_datetime():
                return utils.respondUnauthorized(
                    message=frappe._("Withdraw OTP Expired.")
                )

            lms.token_mark_as_used(token)
        else:
            token = lms.validate_spark_dummy_account_token(
                user.username, data.get("otp"), token_type="Withdraw OTP"
            )

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
        doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
        frappe.enqueue_doc("Notification", "Withdrawal Request", method="send", doc=doc)
        msg = "Dear Customer,\nYour withdrawal request has been received and is under process. We shall reach out to you very soon. Thank you for your patience -Spark Loans"
        if msg:
            receiver_list = list(
                set([str(customer.phone), str(customer.get_kyc().mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        return utils.respondWithSuccess(message=message, data=data)
    except utils.exceptions.APIException as e:
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
                "order_id": "required",
                "loan_margin_shortfall_name": "",
                "is_for_interest": "decimal|between:0,1",
                "is_failed": "",
                "loan_transaction_name": "",
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

        if data.get("order_id"):
            # for order id "-_:" these characters are excluded from regex string
            reg = lms.regex_special_characters(
                search=data.get("order_id"),
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

        msg = ""
        if data.get("is_failed") and data.get("loan_transaction_name"):
            if isinstance(data.get("is_failed"), str):
                data["is_failed"] = dict(data.get("is_failed"))

            loan_transaction = frappe.get_doc(
                "Loan Transaction", data.get("loan_transaction_name")
            )
            if (
                loan_transaction.razorpay_event != "Failed"
                and loan_transaction.status == "Pending"
            ):
                loan_transaction.razorpay_event = "Payment Cancelled"
                loan_transaction.razorpay_payment_log = "\n".join(
                    "<b>{}</b> : {}".format(*i) for i in data.get("is_failed").items()
                )
                loan_transaction.save(ignore_permissions=True)
                frappe.db.commit()
                msg = "Dear Customer,\nSorry! Your payment of Rs. {}  was unsuccessful against loan account  {}. Please check with your bank for details. Spark Loans".format(
                    data.get("amount"), loan.name
                )
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                doc["payment"] = {
                    "amount": data.get("amount"),
                    "loan": loan.name,
                    "is_failed": 1,
                }
                frappe.enqueue_doc(
                    "Notification", "Payment Request", method="send", doc=doc
                )
                receiver_list = list(
                    set([str(customer.phone), str(customer.get_kyc().mobile_number)])
                )
                from frappe.core.doctype.sms_settings.sms_settings import send_sms

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", "Payment failed", fields=["*"]
                )
                lms.send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    message=fcm_notification.message.format(
                        amount=data.get("amount"), loan=loan.name
                    ),
                    loan=loan.name,
                    customer=customer,
                )

                return utils.respondWithSuccess(message="Payment cancelled by user.")

        loan_margin_shortfall = None
        if data.get("loan_margin_shortfall_name", None) and not data.get("is_failed"):
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
            if loan_margin_shortfall.status == "Sell Triggered":
                return utils.respondWithFailure(
                    status=417,
                    message=frappe._("Sale is Triggered"),
                )

        if not data.get("is_failed"):
            frappe.db.begin()
            loan_transaction = loan.create_loan_transaction(
                transaction_type="Payment",
                amount=data.get("amount"),
                order_id=data.get("order_id"),
                loan_margin_shortfall_name=loan_margin_shortfall.name
                if loan_margin_shortfall
                else None,
                is_for_interest=data.get("is_for_interest", None),
            )
            frappe.db.commit()

        if msg:
            receiver_list = list(
                set([str(customer.phone), str(customer.get_kyc().mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        return utils.respondWithSuccess(
            data={"loan_transaction_name": loan_transaction.name}
        )
    except utils.exceptions.APIException as e:
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
                "is_email": "decimal|between:0,1",
                "is_download": "decimal|between:0,1",
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
        user_kyc = lms.__user_kyc()
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

        statement_period = ""
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

            statement_period = (
                from_date.strftime("%d-%B-%Y") + " to " + to_date.strftime("%d-%B-%Y")
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
                statement_period = (
                    curr_month.strftime("%d-%B-%Y")
                    + " to "
                    + frappe.utils.now_datetime().strftime("%d-%B-%Y")
                )
            elif data.get("duration") == "prev_1":
                duration_date = prev_1_month
                statement_period = (
                    prev_1_month.strftime("%d-%B-%Y")
                    + " to "
                    + frappe.utils.now_datetime().strftime("%d-%B-%Y")
                )
            elif data.get("duration") == "prev_3":
                duration_date = prev_3_month
                statement_period = (
                    prev_3_month.strftime("%d-%B-%Y")
                    + " to "
                    + frappe.utils.now_datetime().strftime("%d-%B-%Y")
                )
            elif data.get("duration") == "prev_6":
                duration_date = prev_6_month
                statement_period = (
                    prev_6_month.strftime("%d-%B-%Y")
                    + " to "
                    + frappe.utils.now_datetime().strftime("%d-%B-%Y")
                )
            elif data.get("duration") == "current_year":
                duration_date = current_year
                statement_period = (
                    current_year.strftime("%d-%B-%Y")
                    + " to "
                    + (
                        frappe.utils.add_years(current_year, 1) - timedelta(days=1)
                    ).strftime("%d-%B-%Y")
                )
            else:
                duration_date = datetime.strptime(
                    frappe.utils.today(), "%Y-%m-%d"
                ).date()
                statement_period = (
                    frappe.utils.now_datetime().strftime("%d-%B-%Y")
                    + " to "
                    + frappe.utils.now_datetime().strftime("%d-%B-%Y")
                )

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
        order_by_asc_desc = (
            "asc"
            if data.get("file_format") == "pdf" or data.get("file_format") == "excel"
            else "desc"
        )
        # common data for jinja templating
        lender = frappe.get_doc("Lender", loan.lender)
        las_settings = frappe.get_single("LAS Settings")
        logo_file_path_1 = lender.get_lender_logo_file()
        logo_file_path_2 = las_settings.get_spark_logo_file()
        curr_date = (frappe.utils.now_datetime()).strftime("%d-%B-%Y")
        doc = {
            "username": user_kyc.investor_name,
            "loan_name": loan.name,
            "email": user_kyc.user,
            "customer_id": customer.name,
            # "phone": user_kyc.mobile_number,
            "phone": customer.phone,
            "address": user_kyc.address,
            "account_opening_date": (loan.creation).strftime("%d-%B-%Y"),
            "overdraft_limit": loan.sanctioned_limit,
            "drawing_power": loan.drawing_power,
            "drawing_power_datetime": (frappe.utils.now_datetime()).strftime(
                "%d-%B-%Y %H:%M:%S"
            ),
            "curr_date": curr_date,
            "instrument_type": loan.instrument_type,
            "logo_file_path_1": logo_file_path_1.file_url if logo_file_path_1 else "",
            "logo_file_path_2": logo_file_path_2.file_url if logo_file_path_2 else "",
        }
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
                order_by="time {}".format(order_by_asc_desc),
                fields=[
                    "time",
                    "transaction_type",
                    "name",
                    "record_type",
                    "amount",
                    # "DATE_FORMAT(time, '%Y-%m-%d %H:%i') as time",
                    # "status",
                    "opening_balance",
                    "closing_balance",
                ],
                page_length=page_length,
            )
            if len(loan_transaction_list) <= 0:
                return utils.respondNotFound(message=_("No Record Found"))

            for list in loan_transaction_list:
                list["amount"] = frappe.utils.fmt_money(list["amount"])
                # list["amount"] = lms.amount_formatter(list["amount"])
                list["time"] = list["time"].strftime("%Y-%m-%d %H:%M")
                lt_list.append(list.values())
            # lt_list = [lst.values() for lst in loan_transaction_list]
            res["loan_transaction_list"] = loan_transaction_list
            df = pd.DataFrame(lt_list)
            df.columns = loan_transaction_list[0].keys()
            df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()

            # credit_debit_details = loan.get_transaction_summary()
            loan_account_statement_template = (
                lender.get_loan_account_statement_template()
            )
            # print(sum(df["Amount"].apply(lambda x: float(x))))
            df["Amount"] = (df["Amount"].str.replace(",", "")).apply(lambda x: float(x))
            doc["statement_period"] = statement_period
            doc["summary"] = {
                "debit_count": len(df[df["Record Type"] == "DR"]),
                "credit_count": len(df[df["Record Type"] == "CR"]),
                "total_debit": df.loc[df["Record Type"] == "DR", "Amount"].sum(),
                "total_credit": df.loc[df["Record Type"] == "CR", "Amount"].sum(),
                "opening_balance": df.iloc[0]["Opening Balance"],
                "closing_balance": df.iloc[-1]["Closing Balance"],
            }
            doc["column_name"] = df.columns
            doc["rows"] = df.iterrows()

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
                """select DATE_FORMAT(`tabCollateral Ledger`.creation, '%Y-%m-%d %H:%i') as creation, `tabCollateral Ledger`.isin, `tabSecurity`.security_name, `tabCollateral Ledger`.quantity, `tabCollateral Ledger`.request_type from `tabCollateral Ledger`
            left join `tabSecurity`
            on `tabSecurity`.name = `tabCollateral Ledger`.isin
            where `tabCollateral Ledger`.loan = '{}'
            {}
            order by creation {}
            {}""".format(
                    data.get("loan_name"),
                    "and " + from_to_date
                    if data.get("from_date") and data.get("to_date")
                    else "and " + duration_date
                    if data.get("duration")
                    else "",
                    order_by_asc_desc,
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
            df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()
            loan_account_statement_template = (
                lender.get_pledged_security_statement_template()
            )
            doc["statement_period"] = statement_period
            doc["column_name"] = df.columns
            doc["rows"] = df.iterrows()

            loan_statement_pdf_file = "{}-pledged-securities-transactions.pdf".format(
                data.get("loan_name")
            )
            loan_statement_excel_file = (
                "{}-pledged-securities-transactions.xlsx".format(data.get("loan_name"))
            )

        if data.get("is_download") or data.get("is_email"):
            df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()

            agreement = frappe.render_template(
                loan_account_statement_template.get_content(), {"doc": doc}
            )
            # PDF
            if data.get("file_format") == "pdf":
                loan_statement_pdf_file_path = frappe.utils.get_files_path(
                    loan_statement_pdf_file
                )

                pdf_file = open(loan_statement_pdf_file_path, "wb")
                df.index += 1
                # a = df.to_html()
                # a.replace("dataframe", "center")
                # style = """<style>
                # tr {
                # page-break-inside: avoid;
                # }
                # th {text-align: center;}
                # </style>
                # """

                # html_with_style = style + a

                from frappe.utils.pdf import get_pdf

                if data.get("is_email"):
                    # password content for password protected pdf
                    pwd = user_kyc.pan_no[:4] + str(user_kyc.date_of_birth.year)
                    pdf = get_pdf(
                        agreement,
                        options={
                            "password": pwd,
                            "margin-right": "1mm",
                            "margin-left": "1mm",
                            "page-size": "A4",
                        },
                    )
                else:
                    pdf = get_pdf(
                        agreement,
                        options={
                            "margin-right": "1mm",
                            "margin-left": "1mm",
                            "page-size": "A4",
                        },
                    )

                pdf_file.write(pdf)
                pdf_file.close()

            else:
                # EXCEL
                loan_statement_excel_file_path = frappe.utils.get_files_path(
                    loan_statement_excel_file
                )
                # getting data from html template using BeautifulSoup
                soup = BeautifulSoup(agreement, "lxml")

                # Statement date details
                statement_date_soup = soup.find(
                    "span",
                    attrs={
                        "style": "font-family:Arial, Helvetica, sans-serif; font-size:14px"
                    },
                )
                statement_date_text = statement_date_soup.text
                statement_date_table = pd.Series([statement_date_text])

                # Customer Info table details
                cust_info_soup = soup.find(
                    "table", attrs={"style": "margin-top: 20px;"}
                )
                cust_info_table = cust_info_soup.find_all("tr")
                cust_df = create_df(cust_info_table)

                # Loan transactions/ Pledged securities transactions table details
                data_soup = soup.find("table", attrs={"style": "background:#fff"})
                data_table = data_soup.find_all("tr")
                data_df = create_df(data_table)

                dfs = [statement_date_table, cust_df, data_df]

                if data.get("type") == "Account Statement":
                    # Statement summary title
                    summary_title_soup = soup.find_all(
                        "span",
                        attrs={
                            "style": "font-family:Arial, Helvetica, sans-serif; font-size:14px"
                        },
                    )

                    text = summary_title_soup[1].text
                    summary_title_table = pd.Series([text])
                    dfs.append(summary_title_table)

                    # Statement summary details
                    summary_soup = soup.find(
                        "div", attrs={"style": "margin-top: 10px;"}
                    )
                    summary_table = summary_soup.find_all("tr")
                    summary_df = create_df(summary_table)
                    dfs.append(summary_df)
                    Sheet_name = "Account Statement"

                elif data.get("type") == "Pledged Securities Transactions":
                    Sheet_name = "Pledged Security Statement"

                # Footer details
                email_soup = soup.find_all(
                    "td",
                    attrs={
                        "style": "font-family:Arial, Helvetica, sans-serif; font-size:14px;"
                    },
                )
                e_soup = soup.find_all(
                    "a",
                    attrs={
                        "style": "color:#fff;font-family:Arial, Helvetica, sans-serif; font-size:14px; text-decoration:none"
                    },
                )

                e_text = " " + e_soup[0].text
                footer_lines = [last_txt.text for last_txt in email_soup]
                footer_lines[-1] += e_text
                email_df = pd.Series(footer_lines)
                # email_df = pd.Series([last_txt.text for last_txt in email_soup])
                # e_df = pd.Series([e_text])
                dfs.extend([email_df])

                multiple_dfs(
                    dfs,
                    Sheet_name,
                    loan_statement_excel_file_path,
                    1,
                    lender,
                    las_settings,
                )

                # if data.get("type") == "Account Statement":
                #     # to_numeric(s, downcast='float')
                #     df.columns = ["Date", "Transaction Type", "Ref .No.", "Record Type", "Amount", "Opening Balance", "Closing Balance(₹)"]
                #     # df["Amount"] = frappe.utils.fmt_money(df["Amount"].apply(lambda x: float(x)))
                #     df.loc[df['Record Type'] == "DR", 'Withdrawal (₹)'] = df["Amount"]
                #     df.loc[df['Record Type'] == "CR", 'Deposit (₹)'] = df["Amount"]
                #     df.drop("Opening Balance", inplace=True, axis=1)
                #     df.drop("Record Type", inplace=True, axis=1)
                #     df.drop("Amount", inplace=True, axis=1)
                #     last_column = df.pop('Closing Balance(₹)')
                #     df['Closing Balance(₹)'] = last_column

                # if data.get("type") == "Pledged Securities Transactions":
                #     df.columns = ["Date", "ISIN", "Security Name", "Quantity", "Description"]

                # df.to_excel(loan_statement_excel_file_path, index=False)

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
                    loan_statement_notification = frappe.db.sql(
                        "select message from `tabNotification` where name='Loan Statement PDF';"
                    )[0][0]
                else:
                    with open(loan_statement_excel_file_path, "rb") as fileobj:
                        filedata = fileobj.read()
                    attachments = [
                        {
                            "fname": loan_statement_excel_file,
                            "fcontent": filedata,
                        },
                    ]
                    loan_statement_notification = frappe.db.sql(
                        "select message from `tabNotification` where name='Loan Statement EXCEL';"
                    )[0][0]

                loan_statement_notification = loan_statement_notification.replace(
                    "investor_name", user_kyc.investor_name
                )
                loan_statement_notification = loan_statement_notification.replace(
                    "logo_file",
                    frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
                )
                loan_statement_notification = loan_statement_notification.replace(
                    "fb_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
                )
                loan_statement_notification = loan_statement_notification.replace(
                    "tw_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/tw-icon.png"),
                )
                loan_statement_notification = loan_statement_notification.replace(
                    "inst_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
                )
                loan_statement_notification = loan_statement_notification.replace(
                    "lin_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png"),
                )

                res["is_mail_sent"] = 1
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject="Pledged Securities Transactions for {}".format(loan.name)
                    if data.get("type") == "Pledged Securities Transactions"
                    else "Loan A/c Statement for {}".format(loan.name),
                    message=loan_statement_notification,
                    attachments=attachments,
                )

        return utils.respondWithSuccess(data=res)
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def request_unpledge_otp():
    try:
        utils.validator.validate_http_method("POST")

        user = lms.__user()
        user_kyc = lms.__user_kyc()
        customer = lms.__customer()

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        try:
            loan = frappe.get_last_doc(
                "Loan",
                filters={
                    "customer": customer.name,
                    "instrument_type": "Mutual Fund",
                },
            )
        except frappe.DoesNotExistError:
            loan = None
        token_type = "Unpledge OTP"
        entity = user_kyc.mobile_number
        if customer.cams_email_id and loan:
            token_type = "Revoke OTP"
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
        msg_type = ["unpledge", "pledged securities"]
        if customer.mycams_email_id:
            msg_type = ["revoke", "lien schemes"]
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))

        res = {"loan": loan}

        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None
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
                unpledge_msg_while_margin_shortfall="""OOPS! Dear {}, It seems you have a margin shortfall. You cannot {} any of the {} until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                    loan.get_customer().first_name, msg_type[0], msg_type[1]
                )
                if loan_margin_shortfall
                else None,
                unpledge=loan.max_unpledge_amount(),
            )
        # data = {"loan": loan, "unpledge": unpledge}

        return utils.respondWithSuccess(data=res)
    except utils.exceptions.APIException as e:
        return e.respond()


def validate_securities_for_unpledge(securities, loan, instrument_type="Shares"):
    if not securities or (
        type(securities) is not dict and "list" not in securities.keys()
    ):
        raise utils.exceptions.ValidationException(
            {"securities": {"required": frappe._("Securities required.")}}
        )

    securities = securities["list"]

    if len(securities) == 0:
        raise utils.exceptions.ValidationException(
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
            "select isin from `tabAllowed Security` where lender = '{}' and instrument_type = '{}' and isin in {}".format(
                loan.lender,
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
        raise utils.exceptions.ValidationException(
            {"securities": {"required": message}}
        )

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
        user_kyc = lms.__user_kyc()

        application_type = "Unpledge"
        msg_type = ["unpledge", "pledged securities"]
        token_type = "Unpledge OTP"
        entity = user_kyc.mobile_number
        if customer.mycams_email_id:
            application_type = "Revoke"
            msg_type = ["revoke", "lien schemes"]
            token_type = "Revoke OTP"
            entity = customer.phone

        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            return utils.respondNotFound(message=frappe._("Loan not found."))
        if loan.customer != customer.name:
            return utils.respondForbidden(message=_("Please use your own Loan."))
        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None
        if loan_margin_shortfall:
            return utils.respondWithFailure(
                status=417,
                message="""OOPS! Dear {}, It seems you have a margin shortfall. You cannot {} any of the {} until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                    loan.get_customer().first_name, msg_type[0], msg_type[1]
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
                message="{} Application for {} is already in process.".format(
                    application_type, loan.name
                ),
            )

        securities = validate_securities_for_unpledge(data.get("securities", {}), loan)

        frappe.db.begin()

        user = lms.__user()
        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
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
                "customer_name": customer.full_name,
            }
        )
        unpledge_application.insert(ignore_permissions=True)
        frappe.enqueue_doc(
            "Notification", "Unpledge Request", method="send", doc=user_kyc
        )
        msg = "Dear Customer,\nYour {} request has been successfully received. You shall soon receive a confirmation message. Thank you for your patience. - Spark Loans".format(
            msg_type[0]
        )

        receiver_list = list(
            set([str(customer.phone), str(customer.get_kyc().mobile_number)])
        )
        from frappe.core.doctype.sms_settings.sms_settings import send_sms

        frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        return utils.respondWithSuccess(data=unpledge_application)
    except utils.exceptions.APIException as e:
        return e.respond()


@frappe.whitelist()
def request_sell_collateral_otp():
    try:
        utils.validator.validate_http_method("POST")

        user = lms.__user()
        customer = lms.__customer()

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        try:
            loan = frappe.get_last_doc(
                "Loan",
                filters={
                    "customer": customer.name,
                    "instrument_type": "Mutual Fund",
                },
            )
        except frappe.DoesNotExistError:
            loan = None

        token_type = "Sell Collateral OTP"
        if customer.cams_email_id and loan:
            token_type = "Invoke OTP"
        if not is_dummy_account:
            frappe.db.begin()
            lms.create_user_token(
                entity=user.username,
                token_type=token_type,
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="{} sent".format(token_type))
    except utils.exceptions.APIException as e:
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
        application_type = "Sell Collateral"
        msg_type = ["unpledge", "pledged securities"]
        if customer.mycams_email_id:
            application_type = "Invoke"
            msg_type = ["revoke", "lien schemes"]

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
                message="{} Application for {} is already in process.".format(
                    application_type, loan.name
                ),
            )

        securities = validate_securities_for_sell_collateral(
            data.get("securities", {}), data.get("loan_name")
        )

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        if not is_dummy_account:
            token = lms.verify_user_token(
                entity=user.username,
                token=data.get("otp"),
                token_type="{} OTP".format(application_type),
            )

            if token.expiry <= frappe.utils.now_datetime():
                return utils.respondUnauthorized(
                    message=frappe._("{} OTP Expired.".format(application_type))
                )
        else:
            token = lms.validate_spark_dummy_account_token(
                user.username,
                data.get("otp"),
                token_type="{} OTP".format(application_type),
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
                "customer_name": customer.full_name,
            }
        )
        msg = ""

        if data.get("loan_margin_shortfall_name"):
            sell_collateral_application.loan_margin_shortfall = data.get(
                "loan_margin_shortfall_name"
            )
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", data.get("loan_margin_shortfall_name")
            )
            if loan_margin_shortfall.status == "Sell Triggered":
                return utils.respondWithFailure(
                    status=417,
                    message=frappe._("Sale is Triggered"),
                )
            pending_sell_collateral_application = frappe.get_all(
                "Sell Collateral Application",
                filters={
                    "loan": loan.name,
                    "status": ["not IN", ["Approved", "Rejected"]],
                    "loan_margin_shortfall": loan_margin_shortfall.name,
                },
            )
            if pending_sell_collateral_application:
                return utils.respondWithFailure(
                    status=417,
                    message="Payment for Margin Shortfall of Loan {} is already in process.".format(
                        loan.name
                    ),
                )
            # if loan_margin_shortfall.status == "Request Pending":
            #     return utils.respondWithFailure(
            #         status=417,
            #         message="Payment for Margin Shortfall of Loan {} is already in process.".format(
            #             loan.name
            #         ),
            #     )
            if loan_margin_shortfall.status == "Pending":
                loan_margin_shortfall.status = "Request Pending"
                loan_margin_shortfall.save(ignore_permissions=True)
                frappe.db.commit()
            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            frappe.enqueue_doc(
                "Notification", "Margin Shortfall Action Taken", method="send", doc=doc
            )
            msg = "Dear Customer,\nThank you for taking action against the margin shortfall.\nYou can view the 'Action Taken' summary on the dashboard of the app under margin shortfall banner. Spark Loans"
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Margin shortfall – Action taken",
                fields=["*"],
            )
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification, loan=loan.name, customer=customer
            )

        sell_collateral_application.insert(ignore_permissions=True)

        if not is_dummy_account:
            lms.token_mark_as_used(token)

        frappe.db.commit()
        if not data.get("loan_margin_shortfall_name"):
            msg = "Dear Customer,\nYour sell collateral request has been successfully received. You shall soon receive a confirmation message. Thank you for your patience. - Spark Loans"
        doc = customer.get_kyc().as_dict()
        frappe.enqueue_doc(
            "Notification", "Sell Collateral Request", method="send", doc=doc
        )

        if msg:
            receiver_list = list(
                set([str(customer.phone), str(customer.get_kyc().mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        return utils.respondWithSuccess(data=sell_collateral_application)
    except utils.exceptions.APIException as e:
        return e.respond()


def validate_securities_for_sell_collateral(securities, loan_name):
    if not securities or (
        type(securities) is not dict and "list" not in securities.keys()
    ):
        raise utils.exceptions.ValidationException(
            {"securities": {"required": frappe._("Securities required.")}}
        )

    securities = securities["list"]

    if len(securities) == 0:
        raise utils.exceptions.ValidationException(
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
        raise utils.exceptions.ValidationException(
            {"securities": {"required": message}}
        )

    return securities


def multiple_dfs(df_list, sheets, file_name, spaces, lender, las_settings):
    # Handle multiple dataframe and merging them together in a sheet
    row = 4

    writer = pd.ExcelWriter(file_name)

    for dataframe in df_list:
        dataframe.to_excel(
            writer,
            sheet_name=sheets,
            startrow=row,
            startcol=0,
            index=False,
            header=False,
        )
        row = row + len(dataframe.index) + spaces

    workbook = writer.book
    worksheet = workbook.get_worksheet_by_name(sheets)

    logo_file_path_1 = lender.get_lender_logo_file()
    logo_file_path_2 = las_settings.get_spark_logo_file()

    if logo_file_path_1:
        worksheet.insert_image(
            0, 0, frappe.utils.get_files_path(logo_file_path_1.file_name)
        )
    if logo_file_path_2:
        worksheet.insert_image(
            0, 9, frappe.utils.get_files_path(logo_file_path_2.file_name)
        )

    writer.save()


def create_df(html_table_rows):
    # To create dataframe from html content
    list_data = []

    for tr in html_table_rows:

        td = tr.find_all("td")

        row = [tr.text for tr in td]

        list_data.append(row)

    df = pd.DataFrame(list_data)

    return df
