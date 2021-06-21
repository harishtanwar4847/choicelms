# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime
from random import uniform

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from requests.exceptions import RequestException

import lms


class SecurityPrice(Document):
    def before_save(self):
        if self.price <= 0:
            frappe.throw(_("Security price can not be negative or 0."))


def update_security_prices(securities_dict, session_id):
    try:
        las_settings = frappe.get_single("LAS Settings")
        get_latest_security_price_url = "{}{}".format(
            las_settings.jiffy_host, las_settings.jiffy_security_get_latest_price_uri
        )

        payload = {
            "UserId": session_id,
            "SessionId": session_id,
            "MultipleTokens": ",".join(securities_dict.keys()),
        }
        response = requests.post(get_latest_security_price_url, json=payload)
        response_json = response.json()

        if response.ok and response_json.get("Status") == "Success":
            fields = [
                "name",
                "security",
                "security_name",
                "time",
                "price",
                "creation",
                "modified",
                "owner",
                "modified_by",
            ]
            values = {}
            for security in response_json.get("Response").get("lstMultipleTouchline"):
                isin_tuple = securities_dict.get(
                    "{}@{}".format(security.get("SegmentId"), security.get("Token"))
                )
                isin = isin_tuple[0]
                security_name = isin_tuple[1]
                time = (
                    datetime.strptime(security.get("LUT"), "%d-%m-%Y %H:%M:%S")
                    if security.get("LUT")
                    else frappe.utils.now_datetime()
                )
                price = float(security.get("LTP")) / security.get("PriceDivisor")
                values["{}-{}".format(isin, time)] = (
                    "{}-{}".format(isin, time),
                    isin,
                    security_name,
                    time,
                    price,
                    time,
                    time,
                    "Administrator",
                    "Administrator",
                )

            values_ = list(values.values())
            values_.append(())
            frappe.db.bulk_insert(
                "Security Price", fields=fields, values=values_, ignore_duplicates=True
            )

            # Sauce: https://tableplus.com/blog/2018/11/how-to-update-multiple-rows-at-once-in-mysql.html pt. 3
            # code to update price in security with price received in this api
            data = [str((i[1], i[4])) for i in values.values()]
            query = """
                INSERT INTO `tabSecurity`(name, price)
                VALUES {values}
                ON DUPLICATE KEY UPDATE
                price = VALUES(price);
            """.format(
                values=",".join(data)
            )
            frappe.db.sql(query)

    except (RequestException, Exception) as e:
        frappe.log_error()


@frappe.whitelist()
def update_all_security_prices():
    try:
        chunks = lms.chunk_doctype(doctype="Security", limit=50)
        las_settings = frappe.get_single("LAS Settings")
        session_id_generator_url = "{}{}".format(
            las_settings.jiffy_host, las_settings.jiffy_session_generator_uri
        )

        response = requests.get(session_id_generator_url)
        response_json = response.json()

        if response.ok and response_json.get("Status") == "Success":
            for start in chunks.get("chunks"):
                security_list = frappe.db.get_all(
                    "Security",
                    fields=["name", "security_name", "segment", "token_id"],
                    limit_page_length=chunks.get("limit"),
                    limit_start=start,
                )

                securities_dict = {}
                for i in security_list:
                    securities_dict["{}@{}".format(i.segment, i.token_id)] = (
                        i.name,
                        i.security_name,
                    )

                frappe.enqueue(
                    method="lms.lms.doctype.security_price.security_price.update_security_prices",
                    securities_dict=securities_dict,
                    session_id=response_json.get("Response"),
                    queue="long",
                )

            frappe.enqueue(
                method="lms.lms.doctype.loan.loan.check_all_loans_for_shortfall",
                queue="long",
            )
    except (RequestException, Exception) as e:
        frappe.log_error()
