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
                security_transaction = frappe.get_doc(
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
                        value=i.value,
                        creation_date=frappe.utils.now_datetime(),
                    ),
                ).insert(ignore_permissions=True)
                frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Transaction"),
        )


@frappe.whitelist()
def excel_generator(doc_filters):
    if len(doc_filters) == 2:
        doc_filters = {
            "creation_date": frappe.utils.now_datetime().date() - timedelta(days=1)
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

    # report =  pd.concat([final,
    #          final.groupby(["Loan No"],as_index=False)['Qty','Value'].sum()]).sort_values('Loan No')
    # report.loc[report['Client Name'].isnull(), 'Loan No']
    # report.loc[report['Dpid'].isnull(), 'Loan No']
    # report.loc[report['Date'].isnull(), 'Loan No']
    # report.loc[report['Request Type'].isnull(), 'Loan No']
    # report.loc[report['Isin'].isnull(), 'Loan No'] = 'Total'
    # report.loc[report['Security Name'].isnull(), 'Loan No']
    # report.loc[report['Psn'].isnull(), 'Loan No']
    # report.loc[report['Qty'].isnull(), 'Loan No']
    # report.loc[report['Rate'].isnull(), 'Loan No']

    # final.loc[(final['Loan No'].duplicated() & final['Client Name'].duplicated()), ['Loan No','Client Name']] = ''
    # final.loc[(final['Loan No'].duplicated() & final['Dpid'].duplicated()), ['Loan No','Dpid']] = ''

    # for label, _final in final.groupby(['Loan No','Client Name','Dpid']):
    #     print(label)
    #     print(_final)
    #     print()
    # container = []
    # for label, _final in final.groupby(['Loan No','Client Name','Dpid']):
    #     _final.loc['{label[0]} {label[1]} {label[2]:.} Total'] = final[['Value']].sum()
    #     container.append(_final)

    # report = pd.concat(container)
    # report.loc["Grand Total"] = final[['Value']].sum()
    # report.fillna('')

    # new code
    df_subtotal = final.groupby("Loan No", as_index=False)[["Qty", "Value"]].sum()
    # Join dataframes
    df_new = pd.concat([final, df_subtotal], axis=0, ignore_index=True)
    # Sort
    df_new = df_new.sort_values(["Loan No", "Creation Date"])
    val = final[["Value"]].sum()
    df_new.loc[df_new["Isin"].isnull(), "Loan No"] = "Total"
    # df_new.loc[df_new['Client Name'].isnull(), 'Loan No'] = ' Grand Total'
    df_new.loc["Grand Total"] = val
    # df_new.loc['Grand Total'] = df_new.loc['Grand Total'].fillna("")
    # df_new.loc[(df_new['Loan No'].duplicated() & df_new['Client Name'].duplicated()), ['Loan No','Client Name']] = ''
    # df_new.loc[(df_new['Loan No'].duplicated() & df_new['Dpid'].duplicated()), ['Loan No','Dpid']] = ''
    # print("qty",qty)
    # print("val",val)
    file_name = "security_transaction_{}".format(frappe.utils.now_datetime())
    print("excel_name", df_new)
    return lms.download_file(
        dataframe=df_new, file_name=file_name, file_extention="xlsx"
    )
