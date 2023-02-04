# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
from datetime import timedelta

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class SecurityExposureSummary(Document):
    def get_qty(self, isin):
        qty = frappe.db.sql(
            """select sum(pledged_quantity) from `tabLoan Item` where isin = '{security}' and parenttype ='Loan' """.format(
                security=isin,
            )
        )
        return qty


@frappe.whitelist()
def security_exposure_summary():
    try:
        exposure_doc = frappe.get_last_doc("Security Exposure Summary")
        total_sum = 0
        securities = frappe.get_all("Security", fields=["*"])
        for i in securities:
            qty = exposure_doc.get_qty(i.isin)
            quantity = qty[0][0]
            if quantity:
                total = float(i.price) * float(quantity)
                total_sum += total
        for i in securities:
            qty = exposure_doc.get_qty(i.isin)
            quantity = qty[0][0]
            if quantity:
                security_exposure_summary = frappe.get_doc(
                    dict(
                        doctype="Security Exposure Summary",
                        isin=i.name,
                        security_name=i.security_name,
                        quantity=quantity,
                        rate=i.price,
                        value=(float(quantity) * float(i.price)),
                        exposure_=((float(quantity) * float(i.price)) / total_sum)
                        * 100,
                        creation_date=frappe.utils.now_datetime().date(),
                    ),
                ).insert(ignore_permissions=True)
                frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Exposure Summary"),
        )


@frappe.whitelist()
def excel_generator(doc_filters):
    if len(doc_filters) == 2:
        doc_filters = {
            "creation_date": str(frappe.utils.now_datetime().date() - timedelta(days=1))
        }
    security_exposure_doc = frappe.get_all(
        "Security Exposure Summary",
        filters=doc_filters,
        fields=[
            "isin",
            "security_name",
            "quantity",
            "rate",
            "value",
            "exposure_",
        ],
    )
    if security_exposure_doc == []:
        frappe.throw(("Record does not exist"))
    final = pd.DataFrame([c.values() for c in security_exposure_doc], index=None)
    final.columns = security_exposure_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    report = final.sum(numeric_only=True)
    report = final.iloc[:, [2, 4, 5]].sum()
    final.loc["Grand Total"] = report
    final.loc[final["Isin"].isnull(), "Isin"] = "Total"
    final.fillna("")
    file_name = "security_exposure_{}".format(frappe.utils.now_datetime())
    sheet_name = "Security Exposure Summary"
    return lms.download_file(
        dataframe=final,
        file_name=file_name,
        file_extention="xlsx",
        sheet_name=sheet_name,
    )
