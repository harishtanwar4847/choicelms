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

        log = {
            "url": get_latest_security_price_url,
            "request": payload,
            "response": response_json,
        }

        lms.create_log(log, "security_prices_log")

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
                # if price:
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
    current_hour = frappe.utils.now_datetime().hour
    las_settings = frappe.get_single("LAS Settings")

    if frappe.utils.now_datetime().date() not in lms.holiday_list(
        is_market_holiday=1
    ) and (
        las_settings.market_start_time <= current_hour < las_settings.market_end_time
    ):
        try:
            chunks = lms.chunk_doctype(doctype="Security", limit=50)
            las_settings = frappe.get_single("LAS Settings")
            session_id_generator_url = "{}{}".format(
                las_settings.jiffy_host, las_settings.jiffy_session_generator_uri
            )

            response = requests.get(session_id_generator_url)
            response_json = response.json()
            log = {
                "timestamp": str(frappe.utils.now_datetime()),
                "request_url": session_id_generator_url,
                "response": response_json,
            }

            lms.create_log(log, "jiffy_session_generator_log")

            if response.ok and response_json.get("Status") == "Success":
                for start in chunks.get("chunks"):
                    security_list = frappe.db.get_all(
                        "Security",
                        filters={"instrument_type": "Shares"},
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
    # else:
    #     try:
    #         frappe.enqueue(
    #             method="lms.lms.doctype.loan.loan.check_all_loans_for_shortfall",
    #             queue="long",
    #         )
    #     except Exception as e:
    #         frappe.log_error()


@frappe.whitelist()
def update_all_schemeNav():
    current_hour = frappe.utils.now_datetime().hour
    las_settings = frappe.get_single("LAS Settings")

    if frappe.utils.now_datetime().date() not in lms.holiday_list(
        is_market_holiday=1
    ) and (
        las_settings.market_start_time <= current_hour < las_settings.market_end_time
    ):
        chunks = lms.chunk_doctype(doctype="Security", limit=50)
        for start in chunks.get("chunks"):
            schemes_list = frappe.db.get_all(
                "Security",
                filters={"instrument_type": "Mutual Fund"},
                fields=["isin", "security_name"],
                limit_page_length=chunks.get("limit"),
                limit_start=start,
            )

            frappe.enqueue(
                method="lms.lms.doctype.security_price.security_price.update_scheme_nav",
                schemes_list=schemes_list,
                queue="long",
            )


def update_scheme_nav(schemes_list):
    fields = [
        "name",
        "security",
        "security_name",
        "time",
        "price",
        "navdate",
        "creation",
        "modified",
        "owner",
        "modified_by",
    ]
    values_dict = {}

    for scheme in schemes_list:
        try:
            params = {"isin": scheme["isin"]}
            url = frappe.get_single("LAS Settings").investica_api
            res = requests.get(url=url, params=params)
            req_end_time = str(frappe.utils.now_datetime())
            log = {}
            log[req_end_time] = {"request": params}
            data = res.json()
            log[req_end_time]["response"] = data
            if data["ISIN"] != "":
                ctime = frappe.utils.now_datetime()
                time = (
                    datetime.strptime(data.get("NavDate"), "%d-%m-%Y").replace(
                        hour=ctime.hour, minute=ctime.minute, second=ctime.second
                    )
                    if data.get("NavDate")
                    else frappe.utils.now_datetime()
                )
                values_dict["{}-{}".format(scheme["isin"], time)] = (
                    "{}-{}".format(scheme["isin"], time),
                    scheme["isin"],
                    scheme["security_name"],
                    time,
                    data.get("NAV"),
                    time,
                    time,
                    time,
                    "Administrator",
                    "Administrator",
                )
                lms.create_log(log, "schemes_nav_update_success_log")
            else:
                lms.create_log(log, "schemes_nav_update_failure_log")
        except (RequestException, Exception) as e:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\n\nScheme details-\n{}".format(str(scheme)),
                title="Update scheme nav error",
            )

    if len(values_dict) > 0:
        # bulk insert
        values_list = list(values_dict.values())
        values_list.append(())
        frappe.db.bulk_insert(
            "Security Price", fields=fields, values=values_list, ignore_duplicates=True
        )

        # update price in security list
        # frappe.db.sql(
        #     """
        #     update
        #         `tabSecurity` s, `tabSecurity Price` sp
        #     set
        #         s.price = sp.price
        #     where
        #         s.isin = sp.security
        # """
        # )
        data = [str((i[1], i[4])) for i in values_dict.values()]
        query = """
                INSERT INTO `tabSecurity`(name, price)
                VALUES {values}
                ON DUPLICATE KEY UPDATE
                price = VALUES(price);
            """.format(
            values=",".join(data)
        )
        frappe.db.sql(query)
