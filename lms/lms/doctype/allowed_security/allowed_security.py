# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
import random
import re
import string

import frappe
import requests
import utils
from frappe.model.document import Document
from frappe.utils.csvutils import read_csv_content
from genericpath import exists

import lms


class AllowedSecurity(Document):
    def before_save(self):
        pass
        # if self.eligible_percentage <= 0 or self.eligible_percentage > 100:
        #     frappe.throw(
        #         "Eligible Percentage cannot be less than zero or greater than 100"
        #     )
        # self.security_name = frappe.db.get_value("Security", self.isin, "security_name")
        # if self.instrument_type == "Mutual Fund":
        #     self.update_mycams_scheme()
        # loan_app_list = frappe.get_all(
        #     "Loan Application",
        #     filters={
        #         "status": [
        #             "IN",
        #             [
        #                 "Waiting to be pledged",
        #                 "Pledge executed",
        #                 "Pledge accepted by Lender",
        #             ],
        #         ]
        #     },
        #     fields=["name"],
        # )
        # for doc_name in loan_app_list:
        #     try:
        #         Loan_app_doc = frappe.get_doc("Loan Application", doc_name.name)
        #         for i in Loan_app_doc.items:
        #             if i.isin in self.isin:
        #                 i.eligible_percentage = self.eligible_percentage
        #                 Loan_app_doc.save(ignore_permissions=True)
        #                 frappe.db.commit()
        #         if Loan_app_doc.loan:
        #             l_name = int(Loan_app_doc.loan[2:])
        #             queue = "default" if (l_name % 2) == 0 else "short"
        #             frappe.enqueue_doc(
        #                 "Loan",
        #                 Loan_app_doc.loan,
        #                 method="check_for_shortfall",
        #                 queue=queue,
        #                 on_approval=True,
        #             )

        #     except frappe.DoesNotExistError:
        #         frappe.log_error(
        #             message=frappe.get_traceback(),
        #             title=("Allowed Security get_loan_application"),
        #         )

        # unpledge_application = self.check_unpledge_application()
        # sell_collateral_application = self.check_sell_collateral_application()
        # top_up_application = self.check_topup_application()
        # unpledge_link = ""
        # sell_link = ""
        # topup_link = ""

        # frappe.log_error(
        #     message="unpledge_application  {unpledge_application}".format(
        #         unpledge_application=str(unpledge_application)
        #     )
        #     + "sell_collateral_application  {sell_collateral_application}".format(
        #         sell_collateral_application=str(sell_collateral_application)
        #     )
        #     + "\n top_up_application  {top_up_application}".format(
        #         top_up_application=str(top_up_application)
        #     ),
        #     title=("Allowed Security"),
        # )
        # if unpledge_application:
        #     for unpledge in unpledge_application:
        #         unpledge_link += """<a target="_blank" rel="noreferrer noopener" href="/app/unpledge-application/{unpledge}">{unpledge}</a>""".format(
        #             unpledge=unpledge
        #         )

        # if sell_collateral_application:
        #     for sell in sell_collateral_application:
        #         sell_link += """ <a target="_blank" rel="noreferrer noopener" href="/app/sell-collateral-application/{sell}">{sell}</a>""".format(
        #             sell=sell
        #         )

        # if top_up_application:
        #     for topup in top_up_application:
        #         topup_link += """ <a target="_blank" rel="noreferrer noopener" href="/app/top-up-application/{topup}">{topup}</a>""".format(
        #             topup=topup
        #         )

        # if unpledge_application and sell_collateral_application and top_up_application:
        #     frappe.throw(
        #         """Please approve/reject<br />\u2022 Unpledge Application{}<br />\u2022 Sell Collateral Application{}<br />\u2022 Top up Application{}""".format(
        #             unpledge_link, sell_link, topup_link
        #         )
        #     )

        # if (
        #     unpledge_application
        #     and sell_collateral_application
        #     and not top_up_application
        # ):
        #     frappe.throw(
        #         """Please approve/reject<br />\u2022 Unpledge Application{}<br />\u2022 Sell Collateral Application{}<br />""".format(
        #             unpledge_link,
        #             sell_link,
        #         )
        #     )

        # if (
        #     unpledge_application
        #     and not sell_collateral_application
        #     and top_up_application
        # ):
        #     frappe.throw(
        #         """Please approve/reject<br />\u2022 Unpledge Application{}<br />\u2022 Top up Application{}""".format(
        #             unpledge_link, topup_link
        #         )
        #     )

        # if (
        #     sell_collateral_application
        #     and top_up_application
        #     and not unpledge_application
        # ):
        #     frappe.throw(
        #         """Please approve/reject<br />\u2022 Sell Collateral Application{}<br />\u2022 Top up Application{}""".format(
        #             sell_link, topup_link
        #         )
        #     )

        # if unpledge_application:
        #     frappe.throw(
        #         "Please approve/reject Unpledge Application {}".format(unpledge_link)
        #     )

        # if sell_collateral_application:
        #     frappe.throw(
        #         "Please approve/reject Sell Collateral Application {}".format(sell_link)
        #     )

        # if top_up_application:
        #     frappe.throw(
        #         "Please approve/reject Top Up Application {}".format(topup_link)
        #     )

    def before_insert(self):
        exists_security = frappe.db.exists(
            "Allowed Security", {"isin": self.isin, "lender": self.lender}
        )
        if exists_security:
            frappe.throw(
                frappe._(
                    "ISIN: {} already exists for {}".format(self.isin, self.lender)
                )
            )

    def update_mycams_scheme(self):
        try:
            # LAS Settings Doc
            las_settings = frappe.get_single("LAS Settings")

            datetime_signature = lms.create_signature_mycams()

            # Mycams Allowed Scheme Update API
            url = las_settings.lien_allowed_scheme_update_api

            # Headers
            headers = {
                "Content-Type": "application/json",
                "clientid": las_settings.client_id,
                "datetimestamp": datetime_signature[0],
                "signature": datetime_signature[1],
                "subclientid": "",
            }

            # Request Parameter Data
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

            # Encrypted Request Parameter Data
            encrypted_data = lms.AESCBC(
                las_settings.encryption_key, las_settings.iv
            ).encrypt(json.dumps(data))

            # Request parameter with encrypted request data
            req_data = {"req": str(encrypted_data)}

            resp = requests.post(
                url=url, headers=headers, data=json.dumps(req_data)
            ).text

            # Encrypted response
            encrypted_response = (
                json.loads(resp).get("res").replace("-", "+").replace("_", "/")
            )

            # Decrypted response
            decrypted_response = lms.AESCBC(
                las_settings.decryption_key, las_settings.iv
            ).decrypt(encrypted_response)

            # Decrypted response in Dict format
            dict_decrypted_response = json.loads(decrypted_response)

            # API request-response Log
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
            if lienscheme.get("schemedetails"):
                self.remark = (
                    "Y - " + lienscheme["schemedetails"][0]["status"]
                    if self.allowed
                    else "N - " + lienscheme["schemedetails"][0]["status"]
                )
                if lienscheme["schemedetails"][0]["status"] == "SUCCESS":
                    self.res_status = True
                else:
                    self.res_status = False
                    if self.is_new():
                        self.allowed = False
                    else:
                        if self.allowed:
                            self.allowed = False
                        else:
                            self.allowed = True
            else:
                frappe.throw(frappe._(lienscheme["error"]))
        except requests.RequestException as e:
            frappe.log_error(
                title="Allowed Security Update - Error",
                message=frappe.get_traceback()
                + "\n\nAllowed Security Update Error for isin:\n"
                + str(self.isin),
            )

    def check_unpledge_application(self):
        unpledege_application_list = frappe.get_all(
            "Unpledge Application",
            filters={
                "status": ["IN", ["Pending"]],
            },
            fields=["name"],
        )
        pending_doc = []
        for doc_name in unpledege_application_list:
            try:
                unpledege_application = frappe.get_doc(
                    "Unpledge Application", doc_name.name
                )
                for i in unpledege_application.items:
                    if i.isin in self.isin:
                        pending_doc.append(doc_name.name)

            except frappe.DoesNotExistError:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=("Allowed Security check_unpledge_application"),
                )
        return list(set(pending_doc))

    def check_sell_collateral_application(self):
        sell_collateral_application_list = frappe.get_all(
            "Sell Collateral Application",
            filters={"status": ["IN", ["Pending"]], "processed": 0},
            fields=["name"],
        )
        pending_doc = []
        for doc_name in sell_collateral_application_list:
            try:
                sell_collateral_application = frappe.get_doc(
                    "Sell Collateral Application", doc_name.name
                )
                for i in sell_collateral_application.items:
                    if i.isin in self.isin:
                        pending_doc.append(doc_name.name)

            except frappe.DoesNotExistError:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=("Allowed Security check_sell_collateral_application"),
                )
        return list(set(pending_doc))

    def check_topup_application(self):
        topup_application_list = frappe.get_all(
            "Top up Application",
            filters={
                "status": ["IN", ["Pending", "Esign Done"]],
            },
            fields=["name"],
        )
        pending_doc = []
        for doc_name in topup_application_list:
            try:
                topup_application = frappe.get_doc("Top up Application", doc_name.name)
                loan_doc = frappe.get_doc("Loan", topup_application.loan)
                for i in loan_doc.items:
                    if self.isin == i.isin:
                        pending_doc.append(doc_name.name)

            except frappe.DoesNotExistError:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=("Allowed Security check_topup_application"),
                )
        print("pending_doc", pending_doc)
        return list(set(pending_doc))


@frappe.whitelist()
def update_mycams_scheme_bulk(upload_file):
    files = frappe.get_all("File", filters={"file_url": upload_file}, page_length=1)
    file = frappe.get_doc("File", files[0].name)
    file_path = file.get_full_path()
    with open(file_path, "r") as upfile:
        fcontent = upfile.read()

    csv_data = read_csv_content(fcontent)

    # isin = frappe.db.get_list("Allowed Security", pluck="isin")
    existing_security = frappe.db.get_list(
        "Allowed Security",
        fields=["isin", "lender"],
    )
    exists_scheme = []
    schemedetails = []
    for i in csv_data[1:]:
        # if i[1] in isin:
        # exists_scheme.append(i[1])
        for security in existing_security:
            if i[0] == security["isin"] and i[1] == security["lender"]:
                exists_scheme.append(i[0] + " (" + i[1] + ")")
        schemes = {
            "amccode": i[5],
            "isinno": i[0],
            "approveflag": "Y" if i[9] else "N",
            "lienperc": i[2],
        }
        schemedetails.append(schemes)

    if len(exists_scheme):
        frappe.throw(
            "ISIN: {} {} already exist in Allowed Security List".format(
                ", ".join(isin_scheme for isin_scheme in list(set(exists_scheme))),
                "is" if len(exists_scheme) == 1 else "are",
            )
        )
    try:
        datetime_signature = lms.create_signature_mycams()

        # LAS Settings Doc
        las_settings = frappe.get_single("LAS Settings")

        # Headers
        headers = {
            "Content-Type": "application/json",
            "clientid": las_settings.client_id,
            "datetimestamp": datetime_signature[0],
            "signature": datetime_signature[1],
            "subclientid": "",
        }

        # Mycams Allowed Scheme Update API
        url = las_settings.lien_allowed_scheme_update_api

        # Request Parameter Data
        data = {
            "lienscheme": {
                "clientid": las_settings.client_id,
                "clientname": "",
                "subclientid": "",
                "schemedetails": schemedetails,
            }
        }

        # Encrypted Request Parameter Data
        encrypted_data = lms.AESCBC(
            las_settings.encryption_key, las_settings.iv
        ).encrypt(json.dumps(data))

        # Request parameter with encrypted request data
        req_data = {"req": str(encrypted_data)}

        resp = requests.post(url=url, headers=headers, data=json.dumps(req_data)).text

        # Encrypted response
        encrypted_response = (
            json.loads(resp).get("res").replace("-", "+").replace("_", "/")
        )

        # Decrypted response
        decrypted_response = lms.AESCBC(
            las_settings.decryption_key, las_settings.iv
        ).decrypt(encrypted_response)

        # Decrypted response in Dict format
        dict_decrypted_response = json.loads(decrypted_response)

        # API request-response Log
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
            i[0]: {
                "name": "".join(
                    random.choice(string.ascii_lowercase + string.digits)
                    for _ in range(10)
                ),
                "isin": i[0],
                "lender": i[1],
                "eligible_percentage": i[2],
                "security_category": i[3],
                "instrument_type": i[4],
                "amc_code": i[5],
                "amc_name": i[6],
                "security_name": i[7],
                "scheme_type": i[8],
                "allowed": int(i[9]),
                "creation": frappe.utils.now(),
                "modified": frappe.utils.now(),
                "owner": "Administrator",
                "modified_by": "Administrator",
            }
            for i in csv_data[1:]
        }

        values = []
        lienscheme = dict_decrypted_response["lienscheme"]

        if lienscheme.get("schemedetails"):
            if len(lienscheme["schemedetails"]) == 1:
                scheme = frappe.get_doc(
                    {
                        "doctype": "Allowed Security",
                        "name": "".join(
                            random.choice(string.ascii_lowercase + string.digits)
                            for _ in range(10)
                        ),
                        "isin": i[0],
                        "lender": i[1],
                        "eligible_percentage": i[2],
                        "security_category": i[3],
                        "instrument_type": i[4],
                        "amc_code": i[5],
                        "amc_name": i[6],
                        "security_name": i[7],
                        "scheme_type": i[8],
                        "allowed": int(i[9]),
                        "creation": frappe.utils.now(),
                        "modified": frappe.utils.now(),
                        "owner": "Administrator",
                        "modified_by": "Administrator",
                    }
                ).insert(ignore_permissions=True)
                frappe.db.commit()

            else:
                for i in lienscheme["schemedetails"]:
                    scheme = approved_security_map.get(i["isinno"])
                    scheme["remark"] = (
                        "Y - " + i["status"]
                        if scheme["allowed"]
                        else "N - " + i["status"]
                    )
                    if i["status"] == "SUCCESS":
                        scheme["res_status"] = True
                    else:
                        scheme["res_status"] = False
                        scheme["allowed"] = False
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
