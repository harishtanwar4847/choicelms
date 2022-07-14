# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
import json
import os

import frappe
import numpy as np
import pandas as pd
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
                        qty=i.quantity,
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
    file_name = r"/home/vagrant/spark-bench/sites/security_transaction.xlsx"
    file_path = frappe.utils.get_files_path(file_name)
    if os.path.exists(file_path):
        print(file_path)
        os.remove(file_path)

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
            "creation_date",
            "security_name",
            "psn",
            "qty",
            "rate",
            "value",
        ],
    )
    if security_transaction_doc == []:
        frappe.throw(("Record does not exist"))
    final = pd.DataFrame([c.values() for c in security_transaction_doc], index=None)
    final.columns = security_transaction_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    # final.set_index(['loan_no','client_name','pan_no','sanctioned_amount','pledged_value','drawing_power','loan_balance','adp_shortfall','roi_','client_demat_acc','customer_contact_no','loan_expiry_date','dpd'])
    # report = final.groupby(['']).apply(lambda sub_df:  sub_df.pivot_table(index=['customer','customer_name','transaction_type'], values=['amount'],aggfunc=np.sum, margins=True,margins_name= 'TOTAL'))
    # report.loc[('', 'Grand Total','',''), :] = report[report.index.get_level_values(1) != 'TOTAL'].sum()
    # report=report.reset_index(level=0,drop=True)
    # final
    # report=report.reset_index(level=0,drop=True)

    # report = final.groupby(['Loan No']).apply(lambda sub_df:  sub_df.pivot_table(index=['Client Name','Dpid','Date', 'Request Type','Isin','Creation Date','Security Name','Psn','Qty','Rate'], values=['Value'],aggfunc=np.sum, margins=True,margins_name= 'TOTAL'))
    # report.reset_index(level=0,drop=True)
    # report.loc[('Grand Total','','','','','','','','','','',''), :] = report[report.index.get_level_values(1) != 'TOTAL'].sum()
    # final.drop_duplicates(subset=["Loan No", "Client Name",'Dpid'],keep='first')
    print("abcd", final)
    final.to_excel("security_transaction.xlsx", index=False)

    frappe.local.response.filename = "security_transaction.xlsx"
    with open(
        "/home/vagrant/spark-bench/sites/security_transaction.xlsx", "rb"
    ) as fileobj:
        filedata = fileobj.read()

    frappe.local.response.filecontent = filedata
    frappe.local.response.type = "download"
