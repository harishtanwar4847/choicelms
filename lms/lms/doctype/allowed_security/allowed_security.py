# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
import random
import string

import frappe
import requests
import utils
from frappe.model.document import Document
from frappe.utils.csvutils import read_csv_content

import lms


class AllowedSecurity(Document):
    def before_save(self):
        self.security_name = frappe.db.get_value("Security", self.isin, "security_name")
        self.update_mycams_scheme()

    def update_mycams_scheme(self):
        try:
            las_settings = frappe.get_single("LAS Settings")

            datetime_signature = lms.create_signature_mycams()

            url = las_settings.lien_allowed_scheme_update_api

            headers = {
                "Content-Type": "application/json",
                "clientid": las_settings.client_id,
                "datetimestamp": datetime_signature[0],
                "signature": datetime_signature[1],
                "subclientid": "",
            }

            data = {
                "lienscheme": {
                    "clientid": las_settings.client_id,
                    "clientname": "",
                    "subclientid": "",
                    "schemedetails": [
                        {
                            "amccode": self.amc_code,
                            "isinno": self.isin,
                            "approveflag": "Y" if self.allowed else "N",
                            "lienperc": self.eligible_percentage,
                        }
                    ],
                }
            }

            encrypted_data = lms.AESCBC(
                las_settings.encryption_key, las_settings.iv
            ).encrypt(json.dumps(data))

            req_data = {"req": str(encrypted_data)}

            resp = requests.post(
                url=url, headers=headers, data=json.dumps(req_data)
            ).text

            encrypted_response = (
                json.loads(resp).get("res").replace("-", "+").replace("_", "/")
            )
            decrypted_response = lms.AESCBC(
                las_settings.decryption_key, las_settings.iv
            ).decrypt(encrypted_response)

            dict_decrypted_response = json.loads(decrypted_response)

            lms.create_log(
                {
                    "json_payload": data,
                    "encrypted_request": encrypted_data,
                    "encrypred_response": json.loads(resp).get("res"),
                    "decrypted_response": dict_decrypted_response,
                },
                "approve_security_update",
            )
            lienscheme = dict_decrypted_response["lienscheme"]
            self.remark = (
                "Y - " + lienscheme["error"]
                if self.allowed
                else "N - " + lienscheme["error"]
            )
            if lienscheme and lienscheme["errorcode"] == "S000":
                if lienscheme["schemedetails"][0]["status"] == "SUCCESS":
                    self.res_status = True
                else:
                    self.res_status = False
                    self.allowed = False if self.allowed == True else True
            else:
                self.allowed = False if self.allowed == True else True

        except requests.RequestException as e:
            frappe.log_error(
                title="Allowed Security Update - Error",
                message=frappe.get_traceback()
                + "\n\nAllowed Security Update Error for isin:\n"
                + str(self.isin),
            )


@frappe.whitelist()
def update_mycams_scheme_bulk(upload_file):
    f = frappe.get_all("File", filters={"file_url": upload_file}, page_length=1)
    f = frappe.get_doc("File", f[0].name)
    ff = f.get_full_path()
    with open(ff, "r") as upfile:
        fcontent = upfile.read()

    csv_data = read_csv_content(fcontent)

    schemedetails = []
    for i in csv_data[1:]:
        scheme = {
            "amccode": i[6],
            "isinno": i[1],
            "approveflag": "Y" if i[10] else "N",
            "lienperc": i[3],
        }
        schemedetails.append(scheme)
    try:
        datetime_signature = lms.create_signature_mycams()
        las_settings = frappe.get_single("LAS Settings")
        headers = {
            "Content-Type": "application/json",
            "clientid": las_settings.client_id,
            "datetimestamp": datetime_signature[0],
            "signature": datetime_signature[1],
            "subclientid": "",
        }
        url = las_settings.lien_allowed_scheme_update_api
        data = {
            "lienscheme": {
                "clientid": las_settings.client_id,
                "clientname": "",
                "subclientid": "",
                "schemedetails": schemedetails,
            }
        }

        encrypted_data = lms.AESCBC(
            las_settings.encryption_key, las_settings.iv
        ).encrypt(json.dumps(data))
        req_data = {"req": str(encrypted_data)}
        resp = requests.post(url=url, headers=headers, data=json.dumps(req_data)).text
        encrypted_response = (
            json.loads(resp).get("res").replace("-", "+").replace("_", "/")
        )
        decrypted_response = lms.AESCBC(
            las_settings.decryption_key, las_settings.iv
        ).decrypt(encrypted_response)
        dict_decrypted_response = json.loads(decrypted_response)
        lms.create_log(
            {
                "json_payload": data,
                "encrypted_request": encrypted_data,
                "encrypred_response": json.loads(resp).get("res"),
                "decrypted_response": dict_decrypted_response,
            },
            "approve_security_update",
        )

        fields = [
            "name",
            "isin",
            "lender",
            "eligible_percentage",
            "security_category",
            "instrument_type",
            "amc_code",
            "amc_name",
            "security_name",
            "scheme_type",
            "allowed",
            "creation",
            "modified",
            "owner",
            "modified_by",
            "remark",
            "res_status",
        ]
        approved_security_map = {
            i[1]: {
                "name": "".join(
                    random.choice(string.ascii_lowercase + string.digits)
                    for _ in range(10)
                ),
                "isin": i[1],
                "lender": i[2],
                "eligible_percentage": i[3],
                "security_category": i[4],
                "instrument_type": i[5],
                "amc_code": i[6],
                "amc_name": i[7],
                "security_name": i[8],
                "scheme_type": i[9],
                "allowed": int(i[10]),
                "creation": frappe.utils.now(),
                "modified": frappe.utils.now(),
                "owner": "Administrator",
                "modified_by": "Administrator",
            }
            for i in csv_data[1:]
        }

        values = []
        lienscheme = dict_decrypted_response["lienscheme"]

        if lienscheme and lienscheme["errorcode"] == "S000":
            for i in lienscheme["schemedetails"]:
                scheme = approved_security_map.get(i["isinno"])
                scheme["remark"] = (
                    "Y - " + lienscheme["error"]
                    if scheme["allowed"]
                    else "N - " + lienscheme["error"]
                )
                if i["status"] == "SUCCESS":
                    scheme["res_status"] = True
                else:
                    scheme["res_status"] = False
                    scheme["allowed"] = False if scheme["allowed"] == True else False

                scheme = list(scheme.values())
                values.append(scheme)
        else:
            frappe.throw(frappe._(lienscheme["error"]))
        values.append([])
        frappe.db.bulk_insert(
            "Allowed Security", fields=fields, values=values, ignore_duplicates=False
        )
    except requests.RequestException as e:
        frappe.log_error(
            title="Allowed Security Update - Error",
            message=frappe.get_traceback()
            + "\n\nAllowed Security Update Error for isin\n",
        )
