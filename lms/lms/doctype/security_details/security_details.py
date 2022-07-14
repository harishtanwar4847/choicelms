# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime

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
            customer = frappe.get_doc("Loan Customer", loan.customer)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            loan_application = frappe.get_all(
                "Loan Application",
                filters={"customer": loan.customer},
                fields=["pledgor_boid"],
            )
            pledgor_boid = loan_application[0].pledgor_boid
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
                    pledgor_boid=pledgor_boid,
                    creation_date=frappe.utils.now_datetime(),
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Details"),
        )


@frappe.whitelist()
def excel_generator(doc_filters):
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
    print("abcd")
    final = pd.DataFrame([c.values() for c in seurity_details_doc], index=None)
    final.columns = seurity_details_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    # final.set_index(['loan_no','client_name','pan_no','sanctioned_amount','pledged_value','drawing_power','loan_balance','adp_shortfall','roi_','client_demat_acc','customer_contact_no','loan_expiry_date','dpd'])
    # report = final.groupby(['']).apply(lambda sub_df:  sub_df.pivot_table(index=['customer','customer_name','transaction_type'], values=['amount'],aggfunc=np.sum, margins=True,margins_name= 'TOTAL'))
    # report.loc[('', 'Grand Total','',''), :] = report[report.index.get_level_values(1) != 'TOTAL'].sum()
    # report=report.reset_index(level=0,drop=True)
    # final
    # report=report.reset_index(level=0,drop=True)
    final.to_excel("security_details.xlsx", index=False)
