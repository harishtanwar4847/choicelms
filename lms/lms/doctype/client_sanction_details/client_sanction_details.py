# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import datetime

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class ClientSanctionDetails(Document):
    pass


@frappe.whitelist()
def client_sanction_details():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            customer = frappe.get_doc("Loan Customer", loan.customer)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            interest_config = frappe.get_value(
                "Interest Configuration",
                {
                    "to_amount": [">=", loan.sanctioned_limit],
                },
                order_by="to_amount asc",
            )
            int_config = frappe.get_doc("Interest Configuration", interest_config)
            roi_ = int_config.base_interest * 12
            print("Loan Name", loan.name)
            start_date = frappe.db.sql(
                """select cast(creation as date) from `tabLoan` where name = "{}" """.format(
                    loan.name
                )
            )
            client_sanction_details = frappe.get_doc(
                dict(
                    doctype="Client Sanction Details",
                    client_code=customer.name,
                    loan_no=loan.name,
                    client_name=loan.customer_name,
                    pan_no=user_kyc.pan_no,
                    start_date=start_date,
                    end_date=loan.expiry_date,
                    sanctioned_amount=loan.sanctioned_limit,
                    roi=roi_,
                    creation_date=frappe.utils.now_datetime(),
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Client Sanction Details"),
        )


@frappe.whitelist()
def excel_generator(doc_filters):
    client_sanctioned_details_doc = frappe.get_all(
        "Client Sanction Details",
        filters=doc_filters,
        fields=[
            "client_code",
            "loan_no",
            "client_name",
            "pan_no",
            "start_date",
            "end_date",
            "sanctioned_amount",
            "roi",
        ],
    )
    if client_sanctioned_details_doc == []:
        frappe.throw(("Record does not exist"))

    final = pd.DataFrame(
        [c.values() for c in client_sanctioned_details_doc], index=None
    )
    print(final)
    # final=final.set_index(['client_code', 'loan_no','client_name','pan_no'],drop = False)
    # final = final.set_index(['client_code', 'loan_no','client_name','pan_no','start_date'])
    final.columns = client_sanctioned_details_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    final.sort_values("Client Code", inplace=True)

    # final.set_index(['loan_no','client_name','pan_no','sanctioned_amount','pledged_value','drawing_power','loan_balance','adp_shortfall','roi_','client_demat_acc','customer_contact_no','loan_expiry_date','dpd'])
    # report = final.groupby(['']).apply(lambda sub_df:  sub_df.pivot_table(index=['customer','customer_name','transaction_type'], values=['amount'],aggfunc=np.sum, margins=True,margins_name= 'TOTAL'))
    # report.loc[('', 'Grand Total','',''), :] = report[report.index.get_level_values(1) != 'TOTAL'].sum()
    # report=report.reset_index(level=0,drop=True)
    # final
    # report=report.reset_index(level=0,drop=True)
    final.to_excel("Client_Sanction_Details.xlsx", index=False)
