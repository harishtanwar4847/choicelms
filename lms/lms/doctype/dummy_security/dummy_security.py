# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document
from frappe.utils.csvutils import read_csv_content


class DummySecurity(Document):
    pass


@frappe.whitelist()
def process_csv(upload_file):
    f = frappe.get_all("File", filters={"file_url": upload_file}, page_length=1)
    f = frappe.get_doc("File", f[0].name)
    ff = f.get_full_path()
    with open(ff, "r") as upfile:
        fcontent = upfile.read()

    csv = read_csv_content(fcontent)

    isin = tuple(set(i[1] for i in csv[1:]))
    res = frappe.db.sql(
        "select security_name, price, isin from `tabSecurity` where isin in %s",
        (isin,),
        as_dict=1,
    )
    isin_map = {i.isin: i for i in res}

    fields = [
        "name",
        "isin",
        "scrip_name",
        "stock_at",
        "quantity",
        "price",
        "creation",
        "modified",
        "owner",
        "modified_by",
    ]

    values = []
    for i in csv[1:]:
        curr = isin_map.get(i[1])
        if curr:
            a = curr.get("security_name")
            values.append(
                [
                    i[0] + "-" + i[1],
                    i[1],
                    curr.get("security_name"),
                    i[0],
                    i[2],
                    curr.get("price"),
                    frappe.utils.now(),
                    frappe.utils.now(),
                    "Administrator",
                    "Administrator",
                ]
            )

    values.append([])

    frappe.db.sql("truncate `tabDummy Security`")
    frappe.db.bulk_insert(
        "Dummy Security", fields=fields, values=values, ignore_duplicates=True
    )


@frappe.whitelist(allow_guest=True)
def get_holdings():
    frappe.response.Status = "Success"
    frappe.response.Response = frappe.get_all(
        "Dummy Security",
        fields=[
            "scrip_name as Scrip_Name",
            "isin as ISIN",
            "stock_at as Stock_At",
            "quantity as Quantity",
            "price as Price",
        ],
    )

    return
