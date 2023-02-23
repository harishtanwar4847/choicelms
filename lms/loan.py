import json
import math
import re
from datetime import date, datetime, timedelta
from email import message

import frappe
import pandas as pd
import requests
import utils
from bs4 import BeautifulSoup
from frappe import _
from lxml import etree
from utils.responder import respondWithFailure, respondWithSuccess

import lms
from lms import convert_sec_to_hh_mm_ss, generateResponse, holiday_list
from lms.exceptions import ForbiddenException
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.approved_terms_and_conditions.approved_terms_and_conditions import (
    ApprovedTermsandConditions,
)
from lms.lms.doctype.user_token.user_token import send_sms


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
            # return utils.respondNotFound(message=_("Loan Application not found."))
            raise lms.exceptions.NotFoundException(_("Loan Application not found"))
        if loan_application.customer != customer.name:
            # return utils.respondForbidden(
            #     message=_("Please use your own Loan Application.")
            # )
            raise lms.exceptions.ForbiddenException(
                _("Please use your own Loan Application")
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
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def esign(**kwargs):
    res_params = {}
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_application_name": "",
                "topup_application_name": "",
                "loan_renewal_application_name": "",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_application_name")
            + data.get("topup_application_name")
            + data.get("loan_renewal_application_name")
        )
        if reg:
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        customer = lms.__customer()
        if (
            data.get("loan_application_name")
            and data.get("topup_application_name")
            and data.get("loan_renewal_application_name")
            or data.get("loan_application_name")
            and data.get("topup_application_name")
            or data.get("topup_application_name")
            and data.get("loan_renewal_application_name")
            or data.get("loan_application_name")
            and data.get("loan_renewal_application_name")
        ):
            # return utils.respondForbidden(
            #     message=_("Can not use both application at once, please use one.")
            # )
            raise lms.exceptions.ForbiddenException(
                _("Can not use both application at once, please use one.")
            )

        elif (
            not data.get("loan_application_name")
            and not data.get("topup_application_name")
            and not data.get("loan_renewal_application_name")
        ):
            # return utils.respondForbidden(
            #     message=_(
            #         "Loan Application and Top up Application not found. Please use atleast one."
            #     )
            # )
            raise lms.exceptions.ForbiddenException(
                _(
                    "Loan Application , Top up Application and Loan Renewal Application not found. Please use atleast one."
                )
            )

        if data.get("loan_application_name"):
            loan_application = frappe.get_doc(
                "Loan Application", data.get("loan_application_name")
            )
            if not loan_application:
                # return utils.respondNotFound(message=_("Loan Application not found."))
                raise lms.exceptions.NotFoundException(_("Loan Application not found"))
            if loan_application.customer != customer.name:
                # return utils.respondForbidden(
                #     message=_("Please use your own Loan Application.")
                # )
                raise lms.exceptions.ForbiddenException(
                    _("Please user your own Loan Application.")
                )
            increase_loan = 0
            if loan_application.loan and not loan_application.loan_margin_shortfall:
                increase_loan = 1
            esign_request = loan_application.esign_request(increase_loan)
            application = loan_application

        elif data.get("topup_application_name"):
            topup_application = frappe.get_doc(
                "Top up Application", data.get("topup_application_name")
            )
            if not topup_application:
                # return utils.respondNotFound(message=_("Topup Application not found."))
                raise lms.exceptions.NotFoundException(_("Topup Application not found"))
            if topup_application.customer != customer.name:
                # return utils.respondForbidden(
                #     message=_("Please use your own Topup Application.")
                # )
                raise lms.exceptions.ForbiddenException(
                    _("Please use yor own Topup Application")
                )
            esign_request = topup_application.esign_request()
            application = topup_application

        else:
            loan_renewal_application = frappe.get_doc(
                "Spark Loan Renewal Application",
                data.get("loan_renewal_application_name"),
            )
            if not loan_renewal_application:
                raise lms.exceptions.NotFoundException(
                    _("Loan Renewal Application not found")
                )
            if loan_renewal_application.customer != customer.name:
                raise lms.exceptions.ForbiddenException(
                    _("Please use yor own Loan Renewal Application")
                )
            esign_request = loan_renewal_application.esign_request()
            application = loan_renewal_application

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

            before_esign_file_name = "{}-{}-before-esign.pdf".format(
                application.name, data.get("id")
            )
            before_esign_file_path = frappe.utils.get_files_path(before_esign_file_name)
            before_esign_file_url = frappe.utils.get_url(
                "files/" + before_esign_file_name
            )

            open(before_esign_file_path, "wb").write(
                esign_request.get("files").get("file")[1]
            )

            res_params = {
                "esign_url_dict": esign_request.get("esign_url_dict"),
                "esign_file_upload_url": esign_request.get("file_upload_url"),
                "headers": esign_request.get("headers"),
                "loan_application_name": data.get("loan_application_name"),
                "topup_application_name": data.get("topup_application_name"),
                "loan_renewal_application_name": data.get(
                    "loan_renewal_application_name"
                ),
                "esign_response": res.json(),
                "res_url": url,
                "before_esign_file_url": before_esign_file_url,
            }

            lms.create_log(
                res_params,
                "esign_log",
            )

            before_esign_file_url = """<a href="{0}">{1}</a>""".format(
                before_esign_file_url, before_esign_file_name
            )

            application.add_comment(
                text=before_esign_file_url,
                comment_email=customer.user,
                comment_by=customer.full_name,
            )

            return utils.respondWithSuccess(
                message=_("Esign URL."),
                data={"esign_url": url, "file_id": data.get("id")},
            )
        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))
    except utils.exceptions.APIException as e:
        lms.log_api_error(res_params)
        return e.respond()


@frappe.whitelist()
def esign_done(**kwargs):
    res_params = {}
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_application_name": "",
                "topup_application_name": "",
                "loan_renewal_application_name": "",
                "file_id": "required",
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_application_name")
            + data.get("topup_application_name")
            + data.get("loan_renewal_application_name")
            + data.get("file_id")
        )
        if reg:
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        if data.get("file_id").isspace():
            return utils.respondWithFailure(
                status=422,
                message=frappe._("Space not allowed in file id."),
            )

        user = lms.__user()
        customer = lms.__customer()
        las_settings = frappe.get_single("LAS Settings")

        if (
            data.get("loan_application_name")
            and data.get("topup_application_name")
            and data.get("loan_renewal_application_name")
            or data.get("loan_application_name")
            and data.get("topup_application_name")
            or data.get("topup_application_name")
            and data.get("loan_renewal_application_name")
            or data.get("loan_application_name")
            and data.get("loan_renewal_application_name")
        ):
            # return utils.respondForbidden(
            #     message=_("Can not use both application at once, please use one.")
            # )
            raise lms.exceptions.ForbiddenException(
                _("Can not use multiple application at once, please use one.")
            )

        elif (
            not data.get("loan_application_name")
            and not data.get("topup_application_name")
            and data.get("loan_renewal_application_name")
        ):
            # return utils.respondForbidden(
            #     "Loan Application and Top up Application not found. Please use atleast one."
            # )
            raise lms.exceptions.ForbiddenException(
                _(
                    "Loan Application, Top up Application and Loan Renewal Application not found. Please use atleast one."
                )
            )

        if data.get("loan_application_name"):
            loan_application = frappe.get_doc(
                "Loan Application", data.get("loan_application_name")
            )
            if not loan_application:
                # return utils.respondNotFound(message=_("Loan Application not found."))
                raise lms.exceptions.NotFoundException(_("Loan Application not found"))

            if loan_application.customer != customer.name:
                # return utils.respondForbidden(
                #     message=_("Please use your own Loan Application.")
                # )
                raise lms.exceptions.ForbiddenException(
                    _("Please use your own Loan Application")
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

        elif data.get("topup_application_name"):
            topup_application = frappe.get_doc(
                "Top up Application", data.get("topup_application_name")
            )
            if not topup_application:
                # return utils.respondNotFound(message=_("Topup Application not found."))
                raise lms.exceptions.NotFoundException(_("Topup Application not found"))

            if topup_application.customer != customer.name:
                # return utils.respondForbidden(
                #     message=_("Please use your own Topup Application.")
                # )
                raise lms.exceptions.ForbiddenException(
                    _("Please use your own Topup Application.")
                )
            esigned_pdf_url = "{}{}".format(
                las_settings.esign_host,
                las_settings.enhancement_esign_download_signed_file_uri,
            ).format(file_id=data.get("file_id"))

        else:
            loan_renewal_application = frappe.get_doc(
                "Spark Loan Renewal Application",
                data.get("loan_renewal_application_name"),
            )
            if not loan_renewal_application:
                raise lms.exceptions.NotFoundException(
                    _("Loan Renewal Application not found")
                )

            if loan_renewal_application.customer != customer.name:
                raise lms.exceptions.ForbiddenException(
                    _("Please use your own Loan Renewal Application.")
                )
            esigned_pdf_url = "{}{}".format(
                las_settings.esign_host,
                las_settings.enhancement_esign_download_signed_file_uri,
            ).format(file_id=data.get("file_id"))

        try:
            res = requests.get(esigned_pdf_url, allow_redirects=True)
            # frappe.db.begin()
            res_params = {
                "loan_application_name": data.get("loan_application_name"),
                "topup_application_name": data.get("topup_application_name"),
                "loan_renewal_application_name": data.get(
                    "loan_renewal_application_name"
                ),
                "esign_done_request": esigned_pdf_url,
                "esign_done_response_status": "Success"
                if (str(res.content)).startswith("b'%PDF-")
                else "Failed",
            }
            lms.create_log(res_params, "esign_done_log")

            if (str(res.content)).startswith("b'%PDF-"):
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
                elif data.get("topup_application_name"):
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
                    msg = frappe.get_doc(
                        "Spark SMS Notification", "E-sign was successful"
                    ).message
                    # lms.send_sms_notification(customer=[str(customer.phone)],msg=msg)

                    # msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of your new OD limit. Thank you for your patience. - Spark Loans"
                    receiver_list = [str(customer.phone)]
                    if customer.get_kyc().mob_num:
                        receiver_list.append(str(customer.get_kyc().mob_num))
                    if customer.get_kyc().choice_mob_no:
                        receiver_list.append(str(customer.get_kyc().choice_mob_no))

                    receiver_list = list(set(receiver_list))

                    frappe.enqueue(
                        method=send_sms, receiver_list=receiver_list, msg=msg
                    )

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Topup E-signing was successful",
                        fields=["*"],
                    )
                    lms.send_spark_push_notification(
                        fcm_notification=fcm_notification, customer=customer
                    )

                elif data.get("loan_renewal_application_name"):
                    esigned_file = frappe.get_doc(
                        {
                            "doctype": "File",
                            "file_name": "{}-aggrement.pdf".format(
                                data.get("loan_renewal_application_name")
                            ),
                            "content": res.content,
                            "attached_to_doctype": "Spark Loan Renewal Application",
                            "attached_to_name": data.get(
                                "loan_renewal_application_name"
                            ),
                            "attached_to_field": "customer_esigned_document",
                            "folder": "Home",
                        }
                    )
                    esigned_file.save(ignore_permissions=True)

                    loan_renewal_application.status = "Esign Done"
                    loan_renewal_application.workflow_state = "Esign Done"
                    loan_renewal_application.customer_esigned_document = (
                        esigned_file.file_url
                    )
                    loan_renewal_application.save(ignore_permissions=True)
                    frappe.db.commit()
                    doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()

                    msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of loan renew approval.Thank you for your patience.-Spark Loans"

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal E-signing was successful",
                        fields=["*"],
                    )
                    lms.send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan_renewal_application.loan,
                        customer=customer,
                    )

                    if msg:
                        receiver_list = [str(customer.phone)]
                        if customer.get_kyc().mob_num:
                            receiver_list.append(str(customer.get_kyc().mob_num))
                        if customer.get_kyc().choice_mob_no:
                            receiver_list.append(str(customer.get_kyc().choice_mob_no))

                        receiver_list = list(set(receiver_list))

                        frappe.enqueue(
                            method=send_sms, receiver_list=receiver_list, msg=msg
                        )

                return utils.respondWithSuccess()
            else:
                lms.log_api_error(res_params)
                return utils.respondWithFailure()

        except requests.RequestException as e:
            raise utils.exceptions.APIException(str(e))
    except utils.exceptions.APIException as e:
        lms.log_api_error(res_params)
        return e.respond()


@frappe.whitelist()
def my_loans():
    try:
        customer = lms.__customer()
        user = lms.__user()
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
            loan_cust = frappe.db.get_value(
                "Loan Customer",
                {
                    "user": user.email,
                    "kyc_update": 1,
                    "bank_update": 1,
                },
                "name",
            )
            if not under_process_la and loan_cust:
                data["user_can_pledge"] = 1

        data["total_outstanding"] = float(sum([i.outstanding for i in loans]))
        data["total_sanctioned_limit"] = float(sum([i.sanctioned_limit for i in loans]))
        data["total_drawing_power"] = float(sum([i.drawing_power for i in loans]))
        data["total_total_collateral_value"] = float(
            sum([i.total_collateral_value for i in loans])
        )
        data["total_margin_shortfall"] = float(sum([i.shortfall_c for i in loans]))
        renewal_app_list = []
        for i in loans:
            loan_renewal_list = frappe.get_all(
                "Spark Loan Renewal Application",
                filters={"loan": i.name},
                fields=["name"],
            )
            if loan_renewal_list:
                for i in loan_renewal_list:
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application", i.name
                    )
                    renewal_app_list.append(renewal_doc)
        data["loan_renewal_applications"] = renewal_app_list
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
        lms.log_api_error()
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
        lms.log_api_error()
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
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))
        customer = lms.__customer()
        user_kyc = lms.__user_kyc()
        user = lms.__user()

        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            # return utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))
        if loan.customer != customer.name:
            # return utils.respondForbidden(message=_("Please use your own Loan."))
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan"))

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
            # return utils.respondForbidden(
            #     message=_("Top up for {} is already in process.".format(loan.name))
            # )
            raise lms.exceptions.ForbiddenException(
                _("Top up for {} is already in process.".format(loan.name))
            )
        elif not topup_amt:
            # return utils.respondWithFailure(status=417, message="Top up not available")
            raise lms.exceptions.RespondFailureException(_("Top up not available."))
        elif data.get("topup_amount") <= 0:
            # return utils.respondWithFailure(
            #     status=417, message="Top up amount can not be 0 or less than 0"
            # )
            raise lms.exceptions.RespondFailureException(
                _("Top up amount can not be 0 or less than 0.")
            )
        elif data.get("topup_amount") > topup_amt:
            # return utils.respondWithFailure(
            #     status=417,
            #     message="Top up amount can not be more than Rs. {}".format(topup_amt),
            # )
            raise lms.exceptions.RespondFailureException(
                _(
                    "Top up amount can not be more than Rs. {}".format(topup_amt),
                )
            )
        elif 0.0 < data.get("topup_amount") <= topup_amt:
            current = frappe.utils.now_datetime()
            expiry = frappe.utils.add_years(current, 1) - timedelta(days=1)

            # frappe.db.begin()
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

            msg = frappe.get_doc("Spark SMS Notification", "Top Up Request").message

            # lms.send_sms_notification(customer=[str(customer.phone)],msg=msg)

            # msg = "Dear Customer,\nYour top up request has been successfully received and is under process. We shall reach out to you very soon. Thank you for your patience -Spark Loans"
            receiver_list = [str(customer.phone)]
            if customer.get_kyc().mob_num:
                receiver_list.append(str(customer.get_kyc().mob_num))
            if customer.get_kyc().choice_mob_no:
                receiver_list.append(str(customer.get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

            data = {
                "topup_application_name": topup_application.name,
            }

        return utils.respondWithSuccess(data=data)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
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
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        customer = lms.__customer()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            # return utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))

        if loan.customer != customer.name:
            # return utils.respondForbidden(message=_("Please use your own Loan."))
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan."))

        if not data.get("transactions_per_page", None):
            data["transactions_per_page"] = 15
        if not data.get("transactions_start", None):
            data["transactions_start"] = 0

        lender = frappe.get_doc("Lender", loan.lender)
        invoke_initiate_charges = {
            "invoke_initiate_charge_type": lender.invoke_initiate_charge_type,
            "invoke_initiate_charges": lender.invoke_initiate_charges,
            "invoke_initiate_charges_minimum_amount": lender.invoke_initiate_charges_minimum_amount,
            "invoke_initiate_charges_maximum_amount": lender.invoke_initiate_charges_maximum_amount,
        }

        loan_transactions_list = frappe.db.get_all(
            "Loan Transaction",
            filters={"loan": data.get("loan_name"), "docstatus": 1},
            order_by="time desc",
            fields=[
                "transaction_type",
                "record_type",
                "amount",
                "time",
                "gst_percent",
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
        for items in loan_transactions_list:
            if "GST" in items["transaction_type"]:
                items["transaction_type"] = items["transaction_type"] + " @{}%".format(
                    items["gst_percent"],
                )
            del items["gst_percent"]
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
                        if loan_margin_shortfall.instrument_type == "Shares"
                        else loan_margin_shortfall.minimum_cash_amount
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
                    msg_type = ["unpledge", "pledged securities"]
                    if loan.instrument_type == "Mutual Fund":
                        msg_type = ["revoke", "liened schemes"]

                    action_taken_for_sell = """\nOn {date} we received a {msg} request of Rs. {amount}/- which is under process. \n(Click here to see {msg} summary) """.format(
                        date=(sell_collateral_for_mg_shortfall[0].creation).strftime(
                            "%d.%m.%Y %I:%M %p"
                        ),
                        amount=sell_off_shortfall,
                        msg="invoke"
                        if loan.instrument_type == "Mutual Fund"
                        else "sell collateral",
                    )
                    loan_margin_shortfall["action_taken_msg"] += action_taken_for_sell

                # for margin shortfall action taken message
                if loan_margin_shortfall.instrument_type == "Shares":
                    remaining_shortfall = (
                        loan_margin_shortfall.shortfall
                        - pledged_paid_shortfall
                        - sell_off_shortfall
                        - (
                            cash_paid_shortfall
                            * (100 / loan_margin_shortfall.allowable_ltv)
                        )
                    )
                else:
                    remaining_shortfall = (
                        loan_margin_shortfall.minimum_cash_amount
                        - sell_off_shortfall
                        - cash_paid_shortfall
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

                    if frappe.utils.now_datetime().date() in holidays:
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

            interest = {
                "total_interest_amt": round(interest_total[0]["total_amt"], 2),
                "due_date": due_date.strftime("%d.%m.%Y"),
                "due_date_txt": due_date_txt,
                "info_msg": info_msg,
                "dpd": dpd,
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
            "invoke_charge_details": invoke_initiate_charges
            if loan.instrument_type == "Mutual Fund"
            else {},
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
            msg_type = ["unpledge", "pledged securities"]
            if loan.instrument_type == "Mutual Fund":
                msg_type = ["revoke", "liened schemes"]
            res["unpledge"] = dict(
                unpledge_msg_while_margin_shortfall="""OOPS! Dear {}, It seems you have a margin shortfall. You cannot {} any of the {} until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                    loan.get_customer().first_name, msg_type[0], msg_type[1]
                )
                if loan_margin_shortfall
                else None,
                unpledge=loan.max_unpledge_amount(),
            )

        res["amount_available_for_withdrawal"] = loan.maximum_withdrawable_amount()

        # Pledgor boid of particular loan
        res["pledgor_boid"] = (
            ""
            if loan.instrument_type == "Mutual Fund"
            else frappe.db.get_value(
                "Collateral Ledger", {"loan": loan.name}, "pledgor_boid"
            )
        )

        exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date() - timedelta(
            days=30
        )
        if (
            exp < frappe.utils.now_datetime().date()
            and loan.total_collateral_value > 0
            and len(loan.items) > 0
        ):
            renewal_doc_list = frappe.get_last_doc(
                "Spark Loan Renewal Application", filters={"loan": loan.name}
            )
            res["loan_renewal_is_expired"] = renewal_doc_list.is_expired

        return utils.respondWithSuccess(data=res)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def loan_withdraw_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"loan_name": "required"})

        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        customer = lms.__customer()
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            # return utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))
        if loan.customer != customer.name:
            # return utils.respondForbidden(
            #     message=_("Please use your own Loan Application.")
            # )
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan."))

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
        lms.log_api_error()
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
            # frappe.db.begin()
            lms.create_user_token(
                entity=user.username,
                token_type="Withdraw OTP",
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="Withdraw OTP sent")
    except utils.exceptions.APIException as e:
        lms.log_api_error()
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
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

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
                # return utils.respondUnauthorized(
                #     message=frappe._("Withdraw OTP Expired.")
                # )
                raise lms.exceptions.UnauthorizedException("Withdraw OTP Expired.")

            lms.token_mark_as_used(token)
        else:
            token = lms.validate_spark_dummy_account_token(
                user.username, data.get("otp"), token_type="Withdraw OTP"
            )

        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            # return utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))
        if loan.customer != customer.name:
            # return utils.respondForbidden(
            #     message=_("Please use your own Loan Application.")
            # )
            raise lms.exceptions.ForbiddenException(_("Loan Application not found"))

        # need bank if first withdrawal transaction
        filters = {"loan": loan.name, "transaction_type": "Withdrawal", "docstatus": 1}
        if frappe.db.count("Loan Transaction", filters) == 0 and not data.get(
            "bank_account_name", None
        ):
            # return utils.respondWithFailure(
            #     status=417, message="Need bank account for first withdrawal"
            # )
            raise lms.exceptions.RespondFailureException(
                _("Need bank account for first withdrawal.")
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
            # return utils.respondNotFound(message=frappe._("Bank Account not found."))
            raise lms.exceptions.NotFoundException(_("Bank Account not found"))
        if data.get("bank_account_name") not in [i.name for i in banks]:
            # return utils.respondForbidden(
            #     message=_("Please use your own Bank Account.")
            # )
            raise lms.exceptions.ForbiddenException(
                _("Please use your own Bank Account.")
            )

        # amount validation
        amount = data.get("amount", 0)
        if amount <= 0:
            # return utils.respondWithFailure(
            #     status=417, message="Amount should be more than 0"
            # )
            raise lms.exceptions.RespondFailureException(
                _("Special Characters not allowed.")
            )

        max_withdraw_amount = loan.maximum_withdrawable_amount()
        if amount > max_withdraw_amount:
            # return utils.respondWithFailure(
            #     status=417,
            #     message="Amount can not be more than {}".format(
            #         round(max_withdraw_amount, 2)
            #     ),
            # )
            raise lms.exceptions.RespondFailureException(
                "Amount can not be more than {}".format(round(max_withdraw_amount, 2)),
            )

        # frappe.db.begin()
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

        masked_bank_account_number = lms.user_details_hashing(
            bank_account.account_number
        )
        message = "Great! Your request for withdrawal has been successfully received. The amount shall be credited to your bank account {} within next 24 hours.".format(
            masked_bank_account_number
        )
        doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
        frappe.enqueue_doc("Notification", "Withdrawal Request", method="send", doc=doc)

        msg = frappe.get_doc("Spark SMS Notification", "Withdrawal Request").message

        # msg = "Dear Customer,\nYour withdrawal request has been received and is under process. We shall reach out to you very soon. Thank you for your patience -Spark Loans"
        if msg:
            # lms.send_sms_notification(customer=[str(customer.phone)],msg=msg)
            receiver_list = [str(customer.phone)]
            if customer.get_kyc().mob_num:
                receiver_list.append(str(customer.get_kyc().mob_num))
            if customer.get_kyc().choice_mob_no:
                receiver_list.append(str(customer.get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        return utils.respondWithSuccess(message=message, data=data)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
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
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        if data.get("order_id"):
            # for order id "-_:" these characters are excluded from regex string
            reg = lms.regex_special_characters(
                search=data.get("order_id"),
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

        customer = lms.__customer()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            # raise utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))
        if loan.customer != customer.name:
            # return utils.respondForbidden(message=_("Please use your own Loan."))
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan"))

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
                loan_transaction.db_set("workflow_state", "Rejected")
                loan_transaction.db_set("status", "Rejected")
                loan_transaction.run_post_save_methods()
                msg = frappe.get_doc(
                    "Spark SMS Notification", "Payment Failed"
                ).message.format(data.get("amount"), loan.name)

                # msg = "Dear Customer,\nSorry! Your payment of Rs. {}  was unsuccessful against loan account  {}. Please check with your bank for details. Spark Loans".format(
                #     data.get("amount"), loan.name
                # )
                doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
                doc["payment"] = {
                    "amount": data.get("amount"),
                    "loan": loan.name,
                    "is_failed": 1,
                }
                frappe.enqueue_doc(
                    "Notification", "Payment Request", method="send", doc=doc
                )
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
                # lms.send_sms_notification(customer=[str(customer.phone)],msg=msg)

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
                # raise utils.respondNotFound(
                #     message=_("Loan Margin Shortfall not found.")
                # )
                raise lms.exceptions.NotFoundException(
                    _("Loan Margin Shortfall not found")
                )
            if loan.name != loan_margin_shortfall.loan:
                # return utils.respondForbidden(
                #     message=_("Loan Margin Shortfall should be for the provided loan.")
                # )
                raise lms.exceptions.ForbiddenException(
                    _("Loan Margin Shortfall should be for the provided loan")
                )
            if loan_margin_shortfall.status == "Sell Triggered":
                # return utils.respondWithFailure(
                #     status=417,
                #     message=frappe._("Sale is Triggered"),
                # )
                raise lms.exceptions.RespondFailureException(_("Sale is Triggered."))

        if not data.get("is_failed"):
            # frappe.db.begin()
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
            receiver_list = [str(customer.phone)]
            if customer.get_kyc().mob_num:
                receiver_list.append(str(customer.get_kyc().mob_num))
            if customer.get_kyc().choice_mob_no:
                receiver_list.append(str(customer.get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        return utils.respondWithSuccess(
            data={"loan_transaction_name": loan_transaction.name}
        )
    except utils.exceptions.APIException as e:
        lms.log_api_error()
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
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        if isinstance(data.get("is_download"), str):
            data["is_download"] = int(data.get("is_download"))

        if isinstance(data.get("is_email"), str):
            data["is_email"] = int(data.get("is_email"))

        customer = lms.__customer()
        user_kyc = lms.__user_kyc()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            # raise utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))

        if loan.customer != customer.name:
            # return utils.respondForbidden(message=_("Please use your own Loan."))
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan"))
        if data.get("type") not in [
            "Account Statement",
            "Pledged Securities Transactions",
        ]:
            # return utils.respondNotFound(message=_("Request Type not found."))
            raise lms.exceptions.NotFoundException(_("Request Type not found"))

        filter = (
            {"loan": data.get("loan_name"), "docstatus": 1}
            if data.get("type") == "Account Statement"
            else {"loan": data.get("loan_name")}
        )

        if data.get("is_download") and data.get("is_email"):
            # return utils.respondWithFailure(
            #     message=frappe._(
            #         "Please choose one between download or email transactions at a time."
            #     )
            # )
            raise lms.exceptions.RespondWithFailureException(
                _("Please choose one between download or email transactions at a time.")
            )

        elif (
            (data.get("is_download") or data.get("is_email"))
            and (data.get("from_date") or data.get("to_date"))
            and data.get("duration")
        ):
            # return utils.respondWithFailure(
            #     message=frappe._(
            #         "Please use either 'From date and To date' or Duration"
            #     )
            # )
            raise lms.exceptions.RespondWithFailureException(
                _("Please use either 'From date and To date' or Duration.")
            )

        elif (data.get("from_date") and not data.get("to_date")) or (
            not data.get("from_date") and data.get("to_date")
        ):
            # return utils.respondWithFailure(
            #     message=frappe._("Please use both 'From date and To date'")
            # )
            raise lms.exceptions.RespondWithFailureException(
                _("Please use both 'From date and To date'")
            )

        elif (data.get("is_download") or data.get("is_email")) and (
            not data.get("file_format")
            or data.get("file_format") not in ["pdf", "excel"]
        ):
            # return utils.respondWithFailure(
            #     message=frappe._("Please select PDF/Excel file format")
            # )
            raise lms.exceptions.RespondWithFailureException(
                _("Please select PDF/Excel file format")
            )

        statement_period = ""
        if data.get("from_date") and data.get("to_date"):
            try:
                from_date = datetime.strptime(data.get("from_date"), "%d-%m-%Y")
                to_date = datetime.strptime(data.get("to_date"), "%d-%m-%Y")
            except ValueError:
                # raise utils.respondWithFailure(
                #     status=417,
                #     message=frappe._("Incorrect date format, should be DD-MM-YYYY"),
                # )
                raise lms.exceptions.RespondFailureException(
                    _("Incorrect date format, should be DD-MM-YYYY")
                )

            if from_date > to_date:
                # return utils.respondWithFailure(
                #     message=frappe._("From date cannot be greater than To date")
                # )
                raise lms.exceptions.RespondWithFailureException(
                    _("From date cannot be greater than to date")
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
                # return utils.respondWithFailure(
                #     message=frappe._("Please provide valid Duration")
                # )
                raise lms.exceptions.RespondWithFailureException(
                    _("Please provide valid Duration.")
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
                # return utils.respondWithFailure(
                #     message=frappe._(
                #         "Please use either 'From date and To date' or Duration to proceed"
                #     )
                # )
                raise lms.exceptions.RespondWithFailureException(
                    _(
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
        logo_file_path_2 = lender.get_lender_address_file()
        curr_date = (frappe.utils.now_datetime()).strftime("%d-%B-%Y")
        if user_kyc.address_details:
            address_details = frappe.get_doc(
                "Customer Address Details", user_kyc.address_details
            )
            address = (
                (
                    (str(address_details.perm_line1) + ", ")
                    if address_details.perm_line1
                    else ""
                )
                + (
                    (str(address_details.perm_line2) + ", ")
                    if address_details.perm_line2
                    else ""
                )
                + (
                    (str(address_details.perm_line3) + ", ")
                    if address_details.perm_line3
                    else ""
                )
                + str(address_details.perm_city)
                + ", "
                + str(address_details.perm_dist)
                + ", "
                + str(address_details.perm_state)
                + ", "
                + str(address_details.perm_country)
                + ", "
                + str(address_details.perm_pin)
            )
        else:
            address = ""

        doc = {
            "username": user_kyc.fullname,
            "loan_name": loan.name,
            "email": user_kyc.user,
            "customer_id": customer.name,
            # "phone": user_kyc.mobile_number,
            "phone": customer.phone,
            "address": address,
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
            "is_html": lender.is_html,
            "lender_header": lender.lender_header,
            "lender_footer": lender.lender_footer,
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
                    "gst_percent",
                    # "DATE_FORMAT(time, '%Y-%m-%d %H:%i') as time",
                    # "status",
                    "opening_balance",
                    "closing_balance",
                ],
                page_length=page_length,
            )
            if len(loan_transaction_list) <= 0:
                # return utils.respondNotFound(message=_("No Record Found"))
                raise lms.exceptions.NotFoundException(_("No Record found"))

            for list in loan_transaction_list:
                list["amount"] = frappe.utils.fmt_money(list["amount"])
                # list["amount"] = lms.amount_formatter(list["amount"])
                list["time"] = list["time"].strftime("%Y-%m-%d %H:%M")
                if "GST" in list["transaction_type"]:
                    list["transaction_type"] = list[
                        "transaction_type"
                    ] + " @{}%".format(
                        list["gst_percent"],
                    )
                lt_list.append(list.values())
                del list["gst_percent"]
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
                """select DATE_FORMAT(`tabCollateral Ledger`.creation, '%Y-%m-%d %H:%i') as creation, `tabCollateral Ledger`.isin, `tabSecurity`.security_name, `tabCollateral Ledger`.quantity, `tabCollateral Ledger`.request_type, `tabCollateral Ledger`.folio from `tabCollateral Ledger`
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
                # return utils.respondNotFound(message=_("No Record Found"))
                raise lms.exceptions.NotFoundException(_("No Record Found"))
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

                # from frappe.utils.pdf import get_pdf

                if data.get("is_email"):
                    # password content for password protected pdf
                    pwd = user_kyc.pan_no[:4] + str(user_kyc.date_of_birth.year)
                    pdf = lms.get_pdf(
                        agreement,
                        options={
                            "password": pwd,
                            "margin-right": "1mm",
                            "margin-left": "1mm",
                            "page-size": "A4",
                        },
                    )
                else:
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
                    "investor_name", user_kyc.fullname
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
        lms.log_api_error()
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
        if user_kyc.kyc_type == "CHOICE":
            entity = user_kyc.choice_mob_no
        elif user_kyc.mob_num != "":
            entity = user_kyc.mob_num
        else:
            entity = customer.phone
        if customer.mycams_email_id and loan:
            token_type = "Revoke OTP"
            entity = customer.phone
        if not is_dummy_account:
            # frappe.db.begin()
            lms.create_user_token(
                entity=entity,
                token_type=token_type,
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="{} sent".format(token_type))
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def loan_unpledge_details(**kwargs):
    try:
        utils.validator.validate_http_method("GET")

        data = utils.validator.validate(kwargs, {"loan_name": "required"})

        reg = lms.regex_special_characters(search=data.get("loan_name"))
        if reg:
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        customer = lms.__customer()
        msg_type = ["unpledge", "pledged securities"]
        if customer.mycams_email_id:
            msg_type = ["revoke", "lien schemes"]
        loan = frappe.get_doc("Loan", data.get("loan_name"))
        if not loan:
            # return utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))
        if loan.customer != customer.name:
            # return utils.respondForbidden(message=_("Please use your own Loan."))
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan."))

        lender = frappe.get_doc("Lender", loan.lender)
        revoke_initiate_charges = {
            "revoke_initiate_charge_type": lender.revoke_initiate_charge_type,
            "revoke_initiate_charges": lender.revoke_initiate_charges,
            "revoke_initiate_charges_minimum_amount": lender.revoke_initiate_charges_minimum_amount,
            "revoke_initiate_charges_maximum_amount": lender.revoke_initiate_charges_maximum_amount,
        }

        res = {
            "loan": loan,
            "revoke_charge_details": revoke_initiate_charges
            if loan.instrument_type == "Mutual Fund"
            else {},
        }

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
        lms.log_api_error()
        return e.respond()


def validate_securities_for_unpledge(securities, loan):
    items_type = "Securities" if loan.instrument_type == "Shares" else "Schemes"
    applicaion_type = "Unpledge" if loan.instrument_type == "Shares" else "Revoke"
    if not securities or (
        type(securities) is not dict and "list" not in securities.keys()
    ):
        raise utils.exceptions.ValidationException(
            {
                "securities": {
                    "required": frappe._(
                        "{items_type} required.".format(items_type=items_type)
                    )
                }
            }
        )

    securities = securities["list"]

    if len(securities) == 0:
        raise utils.exceptions.ValidationException(
            {
                "securities": {
                    "required": frappe._(
                        "{items_type} required.".format(items_type=items_type)
                    )
                }
            }
        )

    # check if securities is a list of dict
    securities_valid = True

    if type(securities) is not list:
        securities_valid = False
        message = frappe._(
            "{items_type} should be list of dictionaries".format(
                items_type=items_type.lower()
            )
        )

    duplicate_securities_list = []
    folio_list = []
    folio_clause = ""
    for i in securities:
        if loan.instrument_type == "Mutual Fund":
            if "folio" not in i.keys() or not i.get("folio"):
                securities_valid = False
                message = frappe._("folio not present")
                break
            duplicate_securities_list.append("{}{}".format(i["isin"], i["folio"]))
            folio_list.append(i["folio"])

    if folio_list:
        folio_clause = " and folio in {}".format(
            lms.convert_list_to_tuple_string(folio_list)
        )

    securities_list = [i["isin"] for i in securities]

    if securities_valid:
        if len(set(duplicate_securities_list)) != len(duplicate_securities_list):
            securities_valid = False
            message = frappe._("duplicate isin")

    if securities_valid:
        securities_list_from_db_ = frappe.db.sql(
            "select isin from `tabAllowed Security` where lender = '{}' and instrument_type = '{}' and isin in {}".format(
                loan.lender,
                loan.instrument_type,
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
            "select isin, pledged_quantity, folio from `tabLoan Item` where  parent = '{}' and isin in {}{}".format(
                loan.name,
                lms.convert_list_to_tuple_string(securities_list),
                folio_clause,
            )
        )
        securities_list_from_db = [i[0] for i in securities_list_from_db_]

        diff = list(set(securities_list) - set(securities_list_from_db))
        if diff:
            securities_valid = False
            message = frappe._("{} isin not found".format(",".join(diff)))
        # else:
        #     securities_obj = {}
        #     for i in securities_list_from_db_:
        #         securities_obj[i[0]] = i[1]
        #     for i in securities:
        #         if i["quantity"] > securities_obj[i["isin"]]:
        #             securities_valid = False
        #             message = frappe._(
        #                 "{} quantity for isin {} should not be greater than {}".format(
        #                     applicaion_type, i["isin"], securities_obj[i["isin"]]
        #                 )
        #             )
        #             break

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
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Character not allowed."))

        customer = lms.__customer()
        user_kyc = lms.__user_kyc()

        loan = frappe.get_doc("Loan", data.get("loan_name"))

        msg_type = ["unpledge", "pledged securities"]
        token_type = "Unpledge OTP"
        if user_kyc.kyc_type == "CHOICE":
            entity = user_kyc.choice_mob_no
        elif user_kyc.mob_num != "":
            entity = user_kyc.mob_num
        else:
            entity = customer.phone
        email_subject = "Unpledge Request"
        if loan.instrument_type == "Mutual Fund":
            msg_type = ["revoke", "lien schemes"]
            token_type = "Revoke OTP"
            entity = customer.phone
            email_subject = "Revoke Request"

        if not loan:
            # return utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))
        if loan.customer != customer.name:
            # return utils.respondForbidden(message=_("Please use your own Loan."))
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan"))
        loan_margin_shortfall = loan.get_margin_shortfall()
        if loan_margin_shortfall.get("__islocal", None):
            loan_margin_shortfall = None
        if loan_margin_shortfall:
            # return utils.respondWithFailure(
            #     status=417,
            #     message="""OOPS! Dear {}, It seems you have a margin shortfall. You cannot {} any of the {} until the margin shortfall is made good. Go to: Margin Shortfall""".format(
            #         loan.get_customer().first_name, msg_type[0], msg_type[1]
            #     ),
            # )
            raise lms.exceptions.RespondFailureException(
                _(
                    """OOPS! Dear {}, It seems you have a margin shortfall. You cannot {} any of the {} until the margin shortfall is made good. Go to: Margin Shortfall""".format(
                        loan.get_customer().first_name, msg_type[0], msg_type[1]
                    ),
                )
            )

        unpledge_application_exist = frappe.get_all(
            "Unpledge Application",
            filters={"loan": loan.name, "status": "Pending"},
            order_by="creation desc",
            page_length=1,
        )
        if len(unpledge_application_exist):
            # return utils.respondWithFailure(
            #     status=417,
            #     message="{} Application for {} is already in process.".format(
            #         msg_type[0].title(), loan.name
            #     ),
            # )
            raise lms.exceptions.RespondFailureException(
                "{} Application for {} is already in process.".format(
                    msg_type[0].title(), loan.name
                ),
            )

        securities = validate_securities_for_unpledge(data.get("securities", {}), loan)

        # frappe.db.begin()

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
                # return utils.respondUnauthorized(
                #     message=frappe._("{} Expired.".format(token_type))
                # )
                raise lms.exceptions.UnauthorizedException(
                    _(
                        "{} Expired.".format(token_type),
                    )
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
                    "folio": i["folio"],
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
        frappe.enqueue_doc("Notification", email_subject, method="send", doc=user_kyc)
        msg = frappe.get_doc(
            "Spark SMS Notification", "Unpledged application"
        ).message.format(msg_type[0])
        # lms.send_sms_notification(customer=[str(customer.phone)],msg=msg)
        # msg = "Dear Customer,\nYour {} request has been successfully received. You shall soon receive a confirmation message. Thank you for your patience. - Spark Loans".format(
        #     msg_type[0]
        # )

        receiver_list = [str(customer.phone)]
        if customer.get_kyc().mob_num:
            receiver_list.append(str(customer.get_kyc().mob_num))
        if customer.get_kyc().choice_mob_no:
            receiver_list.append(str(customer.get_kyc().choice_mob_no))

        receiver_list = list(set(receiver_list))

        frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        return utils.respondWithSuccess(data=unpledge_application)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
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
        if customer.mycams_email_id and loan:
            token_type = "Invoke OTP"
        if not is_dummy_account:
            # frappe.db.begin()
            lms.create_user_token(
                entity=user.username,
                token_type=token_type,
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="{} sent".format(token_type))
    except utils.exceptions.APIException as e:
        lms.log_api_error()
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
            # return utils.respondWithFailure(
            #     status=422,
            #     message=frappe._("Special Characters not allowed."),
            # )
            raise lms.exceptions.FailureException(_("Special Characters not allowed"))

        user = lms.__user()
        customer = lms.__customer()
        try:
            loan = frappe.get_doc("Loan", data.get("loan_name"))
        except frappe.DoesNotExistError:
            # return utils.respondNotFound(message=frappe._("Loan not found."))
            raise lms.exceptions.NotFoundException(_("Loan not found"))
        if loan.customer != customer.name:
            # return utils.respondForbidden(message=_("Please use your own Loan."))
            raise lms.exceptions.ForbiddenException(_("Please use your own Loan"))

        # application_type = "Sell Collateral"
        email_subject = "Sell Collateral Request"
        msg_type = "sell collateral"
        if loan.instrument_type == "Mutual Fund":
            # application_type = "Invoke"
            email_subject = "Invoke Request"
            msg_type = "invoke"

        sell_application_exist = frappe.get_all(
            "Sell Collateral Application",
            filters={"loan": loan.name, "status": "Pending"},
            order_by="creation desc",
            page_length=1,
        )
        if len(sell_application_exist):
            # return utils.respondWithFailure(
            #     status=417,
            #     message="{} Application for {} is already in process.".format(
            #         msg_type.title(), loan.name
            #     ),
            # )
            raise lms.exceptions.RespondFailureException(
                _(
                    "{} Application for {} is already in process.".format(
                        msg_type.title(), loan.name
                    ),
                )
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
                token_type="{} OTP".format(msg_type.title()),
            )

            if token.expiry <= frappe.utils.now_datetime():
                # return utils.respondUnauthorized(
                #     message=frappe._("{} OTP Expired.".format(msg_type.title()))
                # )
                raise lms.exceptions.UnauthorizedException(
                    _(
                        "{} OTP Expired.".format(msg_type.title()),
                    )
                )

        else:
            token = lms.validate_spark_dummy_account_token(
                user.username,
                data.get("otp"),
                token_type="{} OTP".format(msg_type.title()),
            )

        # frappe.db.begin()

        items = []
        for i in securities:
            temp = frappe.get_doc(
                {
                    "doctype": "Sell Collateral Application Item",
                    "isin": i["isin"],
                    "quantity": i["quantity"],
                    "folio": i["folio"],
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
                # return utils.respondWithFailure(
                #     status=417,
                #     message=frappe._("Sale is Triggered"),
                # )
                raise lms.exceptions.RespondFailureException(_("Sale is Triggered"))

            pending_sell_collateral_application = frappe.get_all(
                "Sell Collateral Application",
                filters={
                    "loan": loan.name,
                    "status": ["not IN", ["Approved", "Rejected"]],
                    "loan_margin_shortfall": loan_margin_shortfall.name,
                },
            )
            if pending_sell_collateral_application:
                # return utils.respondWithFailure(
                #     status=417,
                #     message="Payment for Margin Shortfall of Loan {} is already in process.".format(
                #         loan.name
                #     ),
                # )
                raise lms.exceptions.RespondFailureException(
                    _(
                        message="Payment for Margin Shortfall of Loan {} is already in process.".format(
                            loan.name
                        ),
                    )
                )
            if loan_margin_shortfall.status == "Pending":
                loan_margin_shortfall.status = "Request Pending"
                loan_margin_shortfall.save(ignore_permissions=True)
                frappe.db.commit()
            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            frappe.enqueue_doc(
                "Notification", "Margin Shortfall Action Taken", method="send", doc=doc
            )
            msg = frappe.get_doc(
                "Spark SMS Notification", "Margin shortfall - action taken"
            ).message
            # msg = "Dear Customer,\nThank you for taking action against the margin shortfall.\nYou can view the 'Action Taken' summary on the dashboard of the app under margin shortfall banner. Spark Loans"
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
            msg = frappe.get_doc(
                "Spark SMS Notification", "Confirmation"
            ).message.format(msg_type)
            # msg = "Dear Customer,\nYour {} request has been successfully received. You shall soon receive a confirmation message. Thank you for your patience. - Spark Loans".format(
            #     msg_type
            # )
        doc = customer.get_kyc().as_dict()

        frappe.enqueue_doc("Notification", email_subject, method="send", doc=doc)

        if msg:
            # lms.send_sms_notification(customer=[str(customer.phone)],msg=msg)
            receiver_list = [str(customer.phone)]
            if customer.get_kyc().mob_num:
                receiver_list.append(str(customer.get_kyc().mob_num))
            if customer.get_kyc().choice_mob_no:
                receiver_list.append(str(customer.get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        return utils.respondWithSuccess(data=sell_collateral_application)
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


def validate_securities_for_sell_collateral(securities, loan_name):
    loan = frappe.get_doc("Loan", loan_name)
    items_type = "Securities" if loan.instrument_type == "Shares" else "Schemes"
    if not securities or (
        type(securities) is not dict and "list" not in securities.keys()
    ):
        raise utils.exceptions.ValidationException(
            {
                "securities": {
                    "required": frappe._(
                        "{items_type} required.".format(items_type=items_type.lower())
                    )
                }
            }
        )

    securities = securities["list"]

    if len(securities) == 0:
        raise utils.exceptions.ValidationException(
            {
                "securities": {
                    "required": frappe._(
                        "{items_type} required.".format(items_type=items_type.lower())
                    )
                }
            }
        )

    # check if securities is a list of dict
    securities_valid = True

    if type(securities) is not list:
        securities_valid = False
        message = frappe._(
            "{items_type} should be list of dictionaries".format(
                items_type=items_type.lower()
            )
        )

    duplicate_securities_list = []
    folio_list = []
    folio_clause = ""
    for i in securities:
        if loan.instrument_type == "Mutual Fund":
            if "folio" not in i.keys() or not i.get("folio"):
                securities_valid = False
                message = frappe._("folio not present")
                break
            duplicate_securities_list.append("{}{}".format(i["isin"], i["folio"]))
            folio_list.append(i["folio"])

    if folio_list:
        folio_clause = " and folio in {}".format(
            lms.convert_list_to_tuple_string(folio_list)
        )

    securities_list = [i["isin"] for i in securities]

    if securities_valid:
        if len(set(duplicate_securities_list)) != len(duplicate_securities_list):
            securities_valid = False
            message = frappe._("duplicate isin")

    if securities_valid:
        securities_list_from_db_ = frappe.db.sql(
            "select isin, folio from `tabLoan Item` where parent = '{}' and isin in {}{}".format(
                loan_name,
                lms.convert_list_to_tuple_string(securities_list),
                folio_clause,
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
                    "items in {items_type} need to be dictionaries".format(
                        items_type=items_type.lower()
                    )
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
    logo_file_path_2 = lender.get_lender_address_file()

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


@frappe.whitelist()
def request_loan_renewal_otp():
    try:
        utils.validator.validate_http_method("POST")

        user = lms.__user()
        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        if not is_dummy_account:
            # frappe.db.begin()
            lms.create_user_token(
                entity=user.username,
                token_type="Loan Renewal OTP",
                token=lms.random_token(length=4, is_numeric=True),
            )
            frappe.db.commit()
        return utils.respondWithSuccess(message="Loan Renewal OTP sent")
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()


@frappe.whitelist()
def verify_loan_renewal_otp(**kwargs):
    try:
        utils.validator.validate_http_method("POST")

        data = utils.validator.validate(
            kwargs,
            {
                "loan_renewal_application_name": "required",
                "otp": ["required", "decimal", utils.validator.rules.LengthRule(4)],
            },
        )

        reg = lms.regex_special_characters(
            search=data.get("loan_renewal_application_name")
        )
        if reg:
            raise lms.exceptions.FailureException(_("Special Characters not allowed."))

        customer = lms.__customer()
        user = lms.__user()

        is_dummy_account = lms.validate_spark_dummy_account(
            user.username, user.name, check_valid=True
        )
        if not is_dummy_account:
            token = lms.verify_user_token(
                entity=user.username,
                token=data.get("otp"),
                token_type="Loan Renewal OTP",
            )

            # if token.expiry <= frappe.utils.now_datetime():
            #     raise lms.exceptions.UnauthorizedException("Loan Renewal OTP Expired.")

            lms.token_mark_as_used(token)
        else:
            token = lms.validate_spark_dummy_account_token(
                user.username, data.get("otp"), token_type="Loan Renewal OTP"
            )

        loan_renewal_app = frappe.get_doc(
            "Spark Loan Renewal Application", data.get("loan_renewal_application_name")
        )

        if not loan_renewal_app:
            raise lms.exceptions.NotFoundException(_("Loan Renewal not found"))

        if loan_renewal_app.customer != customer.name:
            raise lms.exceptions.ForbiddenException(
                _("Loan Renewal Application not found")
            )

        if token:
            loan_renewal_app.status = "Loan Renewal executed"
            loan_renewal_app.workflow_state = "Loan Renewal executed"
            loan_renewal_app.tnc_complete = 1
            loan_renewal_app.tnc_show = 1
            loan_renewal_app.save(ignore_permissions=True)
            frappe.db.commit()

        return utils.respondWithSuccess(
            data={"loan_renewal_application": loan_renewal_app}
        )
    except utils.exceptions.APIException as e:
        lms.log_api_error()
        return e.respond()
