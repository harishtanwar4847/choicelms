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
    pass


@frappe.whitelist()
def security_exposure_summary():
    try:
        securities = frappe.get_all("Security", fields=["*"])
        for security in securities:
            total_sum = frappe.db.sql(
                """select sum(value) from `tabCollateral Ledger` where loan IS NOT NULL"""
            )
            total_sum = total_sum[0][0]
            qty = frappe.db.sql(
                """select sum(quantity) from `tabCollateral Ledger` where isin = "{}" AND loan IS NOT NULL """.format(
                    security.name
                )
            )
            qty = qty[0][0]
            if qty:
                security_exposure_summary = frappe.get_doc(
                    dict(
                        doctype="Security Exposure Summary",
                        isin=security.name,
                        security_name=security.security_name,
                        quantity=qty,
                        rate=security.price,
                        value=(qty * security.price),
                        exposure_=((qty * security.price) / total_sum) * 100,
                        creation_date=frappe.utils.now_datetime(),
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
            "creation_date": frappe.utils.now_datetime().date() - timedelta(days=1)
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
    report = final.iloc[:, 2:6].sum()
    final.loc["Grand Total"] = report
    final.loc[final["Isin"].isnull(), "Isin"] = "Total"
    final.fillna("")
    # final.set_index(['loan_no','client_name','pan_no','sanctioned_amount','pledged_value','drawing_power','loan_balance','adp_shortfall','roi_','client_demat_acc','customer_contact_no','loan_expiry_date','dpd'])
    # report = final.groupby(['']).apply(lambda sub_df:  sub_df.pivot_table(index=['customer','customer_name','transaction_type'], values=['amount'],aggfunc=np.sum, margins=True,margins_name= 'TOTAL'))
    # report.loc[('', 'Grand Total','',''), :] = report[report.index.get_level_values(1) != 'TOTAL'].sum()
    # report=report.reset_index(level=0,drop=True)
    # final
    # report=report.reset_index(level=0,drop=True)
    # final.to_excel("security_exposure_summary.xlsx", index=False)
    file_name = "security_exposure_{}".format(frappe.utils.now_datetime())
    return lms.download_file(
        dataframe=final, file_name=file_name, file_extention="xlsx"
    )
