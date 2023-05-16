# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
from datetime import timedelta

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class ClientSummary(Document):
    pass


@frappe.whitelist()
def client_summary():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            try:
                customer = frappe.get_doc("Loan Customer", loan.customer)
                user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={"customer": loan.customer},
                    fields=["pledgor_boid"],
                )

                pledgor_boid = loan_application[0].pledgor_boid
                interest_config = frappe.get_value(
                    "Interest Configuration",
                    {
                        "to_amount": [">=", loan.sanctioned_limit],
                    },
                    order_by="to_amount asc",
                )
                int_config = frappe.get_doc("Interest Configuration", interest_config)
                roi = round((int_config.base_interest * 12), 2)
                if user_kyc.choice_mob_no:
                    phone = user_kyc.choice_mob_no
                elif user_kyc.choice_mob_no == "":
                    phone = user_kyc.mob_num
                else:
                    phone = customer.phone
                frappe.get_doc(
                    dict(
                        doctype="Client Summary",
                        loan_no=loan.name,
                        client_name=loan.customer_name,
                        pan_no=user_kyc.pan_no,
                        sanctioned_amount=loan.sanctioned_limit,
                        pledged_value=loan.total_collateral_value,
                        drawing_power=loan.drawing_power,
                        loan_balance=loan.balance,
                        adp_shortfall=(loan.drawing_power - loan.balance),
                        roi_=roi,
                        client_demat_acc=pledgor_boid,
                        customer_contact_no=phone,
                        loan_expiry_date=loan.expiry_date,
                        dpd=loan.day_past_due,
                        creation_date=frappe.utils.now_datetime().date(),
                    ),
                ).insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback()
                    + "\n\nCutomer :{} -\n\nloan :{}".format(loan.customer, loan.name),
                    title=frappe._("Client Summary"),
                )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Client Summary"),
        )


def color_negative_red(value):
    if type(value) in [int, float]:
        color = "red" if value < 0 else "black"
        return "color: %s" % color


@frappe.whitelist()
def excel_generator(doc_filters):
    if len(doc_filters) == 2:
        doc_filters = {
            "creation_date": str(frappe.utils.now_datetime().date() - timedelta(days=1))
        }
    client_summary_doc = frappe.get_all(
        "Client Summary",
        filters=doc_filters,
        fields=[
            "loan_no",
            "client_name",
            "pan_no",
            "sanctioned_amount",
            "pledged_value",
            "drawing_power",
            "loan_balance",
            "adp_shortfall",
            "roi_",
            "client_demat_acc",
            "customer_contact_no",
            "loan_expiry_date",
            "dpd",
        ],
    )
    if client_summary_doc == []:
        frappe.throw(("Record does not exist"))

    final = pd.DataFrame([c.values() for c in client_summary_doc], index=None)
    final.columns = client_summary_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    report = final.iloc[:, 3:8].sum()
    final.loc["Total"] = report
    final.fillna("")
    final.loc[final["Loan No"].isnull(), "Loan No"] = "Total"
    final = final.rename(
        columns={final.columns[7]: "Available Drawing Power/Shortfall"}
    )
    final = final.style.applymap(
        color_negative_red,
        subset=pd.IndexSlice[:, ["Available Drawing Power/Shortfall"]],
    )
    file_name = "client_summary_{}".format(frappe.utils.now_datetime())
    sheet_name = "Client Summary"
    return lms.download_file(
        dataframe=final,
        file_name=file_name,
        file_extention="xlsx",
        sheet_name=sheet_name,
    )
