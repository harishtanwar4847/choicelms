# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
from datetime import timedelta

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class SecurityDetails(Document):
    pass


@frappe.whitelist()
def security_details():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            try:
                customer = frappe.get_doc("Loan Customer", loan.customer)
                user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
                collateral_ledger = frappe.get_all(
                    "Collateral Ledger", filters={"loan": loan.name}, fields=["*"]
                )
                for i in collateral_ledger:
                    co_ledger = i
                security_details = frappe.get_doc(
                    dict(
                        doctype="Security Details",
                        loan_no=loan.name,
                        client_name=loan.customer_name,
                        security_category=co_ledger.security_category,
                        isin=co_ledger.isin,
                        security_name=co_ledger.security_name,
                        quantity=co_ledger.quantity,
                        rate=co_ledger.price,
                        value=co_ledger.value,
                        pledgor_boid=co_ledger.pledgor_boid,
                        creation_date=frappe.utils.now_datetime().date(),
                    ),
                ).insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback()
                    + "\n\\n\nCutomer :{} -\n\nloan :{}".format(
                        loan.customer, loan.name
                    ),
                    title=frappe._("Security Details"),
                )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Details"),
        )


@frappe.whitelist()
def excel_generator(doc_filters):
    if len(doc_filters) == 2:
        doc_filters = {
            "creation_date": str(frappe.utils.now_datetime().date() - timedelta(days=1))
        }

    seurity_details_doc = frappe.get_all(
        "Security Details",
        filters=doc_filters,
        fields=[
            "loan_no",
            "client_name",
            "security_category",
            "isin",
            "security_name",
            "quantity",
            "rate",
            "value",
            "pledgor_boid",
        ],
    )
    if seurity_details_doc == []:
        frappe.throw(("Record does not exist"))
    final = pd.DataFrame([c.values() for c in seurity_details_doc], index=None)
    final.columns = seurity_details_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    file_name = "security_details_{}".format(frappe.utils.now_datetime())
    sheet_name = "Security Details"
    return lms.download_file(
        dataframe=final,
        file_name=file_name,
        file_extention="xlsx",
        sheet_name=sheet_name,
    )
