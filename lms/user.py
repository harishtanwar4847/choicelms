import json
from datetime import datetime

import frappe
import pandas as pd
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.utils.password import update_password

import lms
from lms.exceptions.UserKYCNotFoundException import UserKYCNotFoundException
from lms.exceptions.UserNotFoundException import UserNotFoundException
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
        mess = frappe._(
            "Dear "
            + doc.full_name
            + ", You have successfully updated your Finger Print / PIN registration at Spark.Loans!."
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
                "birth_date": "required|date",
                "accept_terms": "required",
            },
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

            frappe.enqueue_doc("Notification", "User KYC", method="send", doc=user)

            mess = frappe._(
                "Dear "
                + user.full_name
                + ",\nCongratulations! \nYour KYC verification is completed. \nYour credit check has to be cleared by our lending partner before you can avail the loan."
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
            securities_list = res_json["Response"]
            securities_list_ = [i["ISIN"] for i in securities_list]
            securities_category_map = lms.get_allowed_securities(
                securities_list_, data.get("lender")
            )

            for i in securities_list:
                try:
                    i["Category"] = securities_category_map[i["ISIN"]].get("category")
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
def dashboard():
    user = frappe.get_doc("User", frappe.session.user)

    customer = lms.__customer(user.name)
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
                "start": "",
                "per_page": "",
                "search": "",
                "is_download": "",
            },
        )
        # if isinstance(data.get("per_page"),str):
        #     data["per_page"] = int(data.get("per_page"))

        if isinstance(data.get("is_download"), str):
            data["is_download"] = int(data.get("is_download"))

        print(kwargs, data)

        if not data.get("lender"):
            data["lender"] = frappe.get_last_doc("Lender").name

        security_category_list_ = frappe.db.get_all(
            "Allowed Security",
            fields=["distinct(security_category)"],
            order_by="security_category asc",
        )
        security_category_list = [i.security_category for i in security_category_list_]

        or_filters = ""
        if data.get("search", None):
            # or_filters = str(" and ")
            # or_filters += str(
            #     "(allowed.isin like '{search_key}' or master.security_name like '{search_key}' or master.category like '{search_key}')".format(
            #         search_key=search_key
            #     )
            # )
            search_key = ["like", str("%" + data["search"] + "%")]
            or_filters = {
                "isin": search_key,
                "security_name": search_key,
                "security_category": search_key,
            }

        # query = "select allowed.isin, master.security_name, allowed.eligible_percentage, master.category from `tabAllowed Security` allowed left join `tabSecurity` master on allowed.isin = master.isin where allowed.lender = '{}' {}".format(
        #     data.get("lender"), or_filters
        # )

        # approved_security_list = frappe.db.sql(query, as_dict=1)
        approved_security_list = []
        approved_security_pdf_file_url = ""

        if data.get("is_download"):
            approved_security_list = frappe.db.get_all(
                "Allowed Security",
                filters={"lender": data.get("lender")},
                or_filters=or_filters,
                order_by="creation desc",
                fields=[
                    "isin",
                    "security_name",
                    "security_category",
                    "eligible_percentage",
                ],
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
                </style>
                """

            html_with_style = style + a

            from frappe.utils.pdf import get_pdf

            pdf = get_pdf(a)
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
                filters={"lender": data.get("lender")},
                or_filters=or_filters,
                order_by="creation desc",
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
