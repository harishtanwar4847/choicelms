import json
import re
from dataclasses import fields
from datetime import datetime
from random import choice, randint

import frappe
import requests

import lms


def execute():
    try:
        all_kyc = []
        frappe.reload_doc("Lms", "DocType", "CKYC API Response")
        frappe.reload_doc("Lms", "DocType", "User KYC")
        frappe.reload_doc("Lms", "DocType", "Customer Address Details")
        frappe.reload_doc("Lms", "DocType", "User Bank Account")
        frappe.reload_doc("Lms", "DocType", "CKYC Image Details")
        frappe.reload_doc("Lms", "DocType", "Related Person Details")
        frappe.reload_doc("Lms", "DocType", "CKYC Identity Details")

        if frappe.utils.get_url() == "https://spark.loans":
            user_kyc = frappe.get_all(
                "User KYC",
                filters={"consent_given": 0},
                fields=["*"],
            )
        else:
            user_kyc = frappe.get_all(
                "User KYC",
                filters={"consent_given": 0, "pan_no": "CEFPC3206R"},
                fields=["*"],
            )

        for kyc in user_kyc:
            cust = frappe.db.get_value("Loan Customer", {"user": kyc.user}, "name")
            customer = frappe.get_doc("Loan Customer", cust)
            req_data = {
                "idType": "C",
                "idNumber": kyc.pan_no,
                "dateTime": datetime.strftime(
                    frappe.utils.now_datetime(), "%d-%m-%Y %H:%M:%S"
                ),
                "requestId": datetime.strftime(frappe.utils.now_datetime(), "%d%m")
                + str(abs(randint(0, 9999) - randint(1, 99))),
            }

            las_settings = frappe.get_single("LAS Settings")
            headers = {"Content-Type": "application/json"}

            url = las_settings.ckyc_search_api
            res = requests.post(url=url, headers=headers, data=json.dumps(req_data))
            res_json = json.loads(res.text)
            log = {"url": url, "headers": headers, "request": req_data}
            frappe.get_doc(
                {
                    "doctype": "CKYC API Response",
                    "ckyc_api_type": "CKYC Search",
                    "parameters": str(req_data),
                    "response_status": "Success"
                    if res_json.get("status") == 200 and not res_json.get("error")
                    else "Failure",
                    "error": res_json.get("error"),
                    "customer": cust,
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()
            log["response"] = res_json
            lms.create_log(log, "ckyc_search_patch")
            if res_json.get("status") == 200 and not res_json.get("error"):
                req_data.update(
                    {
                        "dob": kyc.date_of_birth.strftime("%d-%m-%Y"),
                        "ckycNumber": json.loads(res_json.get("data"))
                        .get("PID_DATA")
                        .get("SearchResponsePID")
                        .get("CKYC_NO"),
                    }
                )

                url = las_settings.ckyc_download_api

                headers = {"Content-Type": "application/json"}

                res = requests.post(url=url, headers=headers, data=json.dumps(req_data))
                res_json = json.loads(res.text)

                log = {"url": url, "headers": headers, "request": req_data}
                frappe.get_doc(
                    {
                        "doctype": "CKYC API Response",
                        "ckyc_api_type": "CKYC Download",
                        "parameters": str(log),
                        "response_status": "Success"
                        if res_json.get("status") == 200 and not res_json.get("error")
                        else "Failure",
                        "error": res_json.get("error"),
                        "customer": cust,
                    }
                ).insert(ignore_permissions=True)
                frappe.db.commit()
                log["response"] = res_json

                lms.create_log(log, "ckyc_download_patch")

                pid_data = {}
                if res_json.get("status") == 200 and not res_json.get("error"):
                    pid_data = json.loads(res_json.get("data")).get("PID_DATA")

                    personal_details = pid_data.get("PERSONAL_DETAILS")
                    identity_details = pid_data.get("IDENTITY_DETAILS")
                    related_person_details = pid_data.get("RELATED_PERSON_DETAILS")
                    image_details = pid_data.get("IMAGE_DETAILS")

                    user_kyc = frappe.get_doc("User KYC", kyc.name)
                    user_kyc.update(
                        {
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

                    user_address_details = frappe.get_doc(
                        {
                            "doctype": "Customer Address Details",
                            "perm_line1": user_kyc.perm_line1,
                            "perm_line2": user_kyc.perm_line2,
                            "perm_line3": user_kyc.perm_line3,
                            "perm_city": user_kyc.perm_city,
                            "perm_dist": user_kyc.perm_dist,
                            "perm_state": user_kyc.perm_state_name,
                            "perm_country": user_kyc.perm_country_name,
                            "perm_pin": user_kyc.perm_pin,
                            "perm_poa": frappe.db.get_value(
                                "Proof of Address Master",
                                {"name": user_kyc.perm_poa},
                                "poa_name",
                            ),
                            "perm_corres_flag": user_kyc.perm_corres_sameflag,
                            "corres_line1": user_kyc.corres_line1,
                            "corres_line2": user_kyc.corres_line2,
                            "corres_line3": user_kyc.corres_line3,
                            "corres_city": user_kyc.corres_city,
                            "corres_dist": user_kyc.corres_dist,
                            "corres_state": user_kyc.corres_state_name,
                            "corres_country": user_kyc.corres_country_name,
                            "corres_pin": user_kyc.corres_pin,
                            "corres_poa": frappe.db.get_value(
                                "Proof of Address Master",
                                {"name": user_kyc.corres_poa},
                                "poa_name",
                            ),
                        }
                    ).insert(ignore_permissions=True)
                    user_kyc.address_details = user_address_details.name
                    user_kyc.save(ignore_permissions=True)
                    frappe.db.commit()
                    all_kyc.append(user_kyc.name)
                    loan_doc = frappe.get_all(
                        "Loan Customer",
                        filters={"user": user_kyc.user},
                        fields=["loan_open", "bank_update"],
                    )
                    bank_doc = frappe.get_all(
                        "User Bank Account",
                        filters={"parent": user_kyc.name, "is_default": 1},
                        fields=["*"],
                    )
                    if loan_doc[0].loan_open == 1:
                        if len(bank_doc) != 0:
                            frappe.db.sql(
                                "update `tabUser Bank Account` set bank_status='Approved',notification_sent=1 where name = '{}'".format(
                                    (bank_doc[0].name)
                                )
                            )
                            frappe.db.sql(
                                "update `tabLoan Customer` set bank_update=1 where user = '{}'".format(
                                    (user_kyc.user)
                                )
                            )

                else:
                    frappe.db.rollback()
                    frappe.log_error(
                        message=str(res_json)
                        + "\n\nuser_kyc  -\n{}\n\ncustomer - {} ".format(
                            kyc.name, customer.name
                        ),
                        title="ckyc download",
                    )
                    # frappe.(mess=)
            else:
                # lms.log_api_error(mess=str(res_json))
                frappe.log_error(
                    message=str(res_json)
                    + "\n\nuser_kyc  -\n{}\n\ncustomer - {} ".format(
                        kyc.name, customer.name
                    ),
                    title="ckyc download",
                )
        frappe.db.sql(
            "update `tabUser KYC` set kyc_status='Approved',notification_sent=1, consent_given=1 where name in {}".format(
                lms.convert_list_to_tuple_string(all_kyc)
            )
        )
    except Exception as e:
        lms.log_api_error(str(e.args))
