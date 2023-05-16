# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
import json
import os
from datetime import timedelta

import frappe
import numpy as np
import pandas as pd
from black import Report
from frappe.model.document import Document

import lms


class SecurityTransaction(Document):
    pass


@frappe.whitelist()
def security_transaction():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            try:
                collateral_ledger = frappe.get_all(
                    "Collateral Ledger", filters={"loan": loan.name}, fields=["*"]
                )
                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={"customer": loan.customer},
                    fields=["pledgor_boid"],
                )
                pledgor_boid = loan_application[0].pledgor_boid
                for i in collateral_ledger:
                    if i.request_type != "Pledge":
                        qty = -(i.quantity)
                    else:
                        qty = i.quantity
                    frappe.get_doc(
                        dict(
                            doctype="Security Transaction",
                            loan_no=loan.name,
                            client_name=loan.customer_name,
                            dpid=pledgor_boid,
                            date=i.creation.date(),
                            request_type=i.request_type,
                            isin=i.isin,
                            security_name=i.security_name,
                            psn=i.psn,
                            qty=qty,
                            rate=i.price,
                            value=-(i.value) if qty < 0 else i.value,
                            creation_date=frappe.utils.now_datetime().date(),
                        ),
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback()
                    + "\n\nCutomer :{} -\n\nloan :{}".format(loan.customer, loan.name),
                    title=frappe._("Security Transaction"),
                )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Transaction"),
        )


def color_negative_red(objects):
    if type(objects) in [int, float]:
        color = "red" if objects < 0 else "black"
        return "color: %s" % color


@frappe.whitelist()
def excel_generator(doc_filters):
    if len(doc_filters) == 2:
        doc_filters = {
            "creation_date": str(frappe.utils.now_datetime().date() - timedelta(days=1))
        }
    security_transaction_doc = frappe.get_all(
        "Security Transaction",
        filters=doc_filters,
        fields=[
            "loan_no",
            "client_name",
            "dpid",
            "date",
            "request_type",
            "isin",
            "security_name",
            "psn",
            "qty",
            "rate",
            "creation_date",
            "value",
        ],
    )
    if security_transaction_doc == []:
        frappe.throw(("Record does not exist"))
    final = pd.DataFrame([c.values() for c in security_transaction_doc], index=None)
    final.columns = security_transaction_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()

    df_subtotal = final.groupby("Loan No", as_index=False)[["Qty", "Value"]].sum()
    # Join dataframes
    df_new = pd.concat([final, df_subtotal], axis=0, ignore_index=True)
    # Sort
    df_new = df_new.sort_values(["Loan No", "Creation Date"])
    val = final[["Value"]].sum()
    df_new.loc[
        (
            df_new["Loan No"].duplicated()
            & df_new["Client Name"].duplicated()
            & df_new["Dpid"].duplicated()
        ),
        ["Loan No", "Client Name", "Dpid"],
    ] = ""
    df_new.loc[df_new["Isin"].isnull(), "Loan No"] = "Total"
    df_new.loc[len(df_new)] = [
        "Grand Total",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        float(val),
    ]
    df_new.drop("Creation Date", axis=1, inplace=True)
    df_new = df_new.style.applymap(
        color_negative_red,
        subset=pd.IndexSlice[:, ["Value"]],
    )
    file_name = "security_transaction_{}".format(frappe.utils.now_datetime())
    sheet_name = "Security Transaction"
    return lms.download_file(
        dataframe=df_new,
        file_name=file_name,
        file_extention="xlsx",
        sheet_name=sheet_name,
    )
