# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import frappe
import requests
import utils
from frappe.model.document import Document
from frappe.utils.csvutils import read_csv_content

import lms

# import utils
# import random


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
