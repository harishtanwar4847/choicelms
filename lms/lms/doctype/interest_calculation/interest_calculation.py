# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
from datetime import datetime, timedelta

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class InterestCalculation(Document):
    pass


def interest_calculation(loan):
    interest_calculation_list = []
    transactions = frappe.db.sql(
        """select time, transaction_type, record_type, amount, disbursed, closing_balance from `tabLoan Transaction` where loan = "{}" AND month(time) = month(now())""".format(
            loan.name
        ),
        as_dict=True,
    )
    interests = frappe.db.sql(
        """select time, loan_balance, base_amount, rebate_interest from `tabVirtual Interest` where loan = "{}" AND month(time) = month(now())""".format(
            loan.name
        ),
        as_dict=True,
    )
    for transaction in transactions:
        frappe.logger().info(transaction.time)
        if transaction.record_type == "DR":
            credit = 0
            debit = (
                transaction.disbursed
                if transaction.transaction_type == "Withdraw"
                else transaction.amount
            )
        else:
            credit = transaction.amount
            debit = 0
        interest_calculation_list.append(
            dict(
                doctype="Interest Calculation",
                loan_no=loan.name,
                client_name=loan.customer_name,
                date=transaction.time.date(),
                transaction_type=transaction.transaction_type,
                crdr=transaction.record_type,
                debit=debit,
                credit=credit,
                loan_balance=transaction.closing_balance,
                interest_with_rebate=0,
                interest_without_rebate=0,
                creation_date=frappe.utils.now_datetime().date(),
            )
        )
    for interest in interests:
        frappe.logger().info(interest.time)
        index = [
            i
            for i, _ in enumerate(interest_calculation_list)
            if _["date"] == interest.time.date()
        ]
        rebate = interest.base_amount + interest.rebate_interest
        if index:
            interest_calculation_list[index[0]].update(
                [
                    ("loan_balance", interest.loan_balance),
                    ("interest_with_rebate", rebate),
                    ("interest_without_rebate", interest.base_amount),
                ]
            )
        else:
            interest_calculation_list.append(
                dict(
                    doctype="Interest Calculation",
                    loan_no=loan.name,
                    client_name=loan.customer_name,
                    date=interest.time.date(),
                    transaction_type="-",
                    crdr="-",
                    credit="-",
                    debit="-",
                    loan_balance=interest.loan_balance,
                    interest_with_rebate=rebate,
                    interest_without_rebate=interest.base_amount,
                    creation_date=frappe.utils.now_datetime().date(),
                )
            )
    interest_calculation_list.sort(
        key=lambda item: (item["loan_no"], item["date"]), reverse=True
    )
    for i in interest_calculation_list:
        frappe.get_doc(i).insert(ignore_permissions=True)
        frappe.db.commit()


@frappe.whitelist()
def excel_generator(doc_filters):
    if len(doc_filters) == 2:
        doc_filters = {
            "creation_date": str(frappe.utils.now_datetime().date() - timedelta(days=1))
        }

    interest_calculation_doc = frappe.get_all(
        "Interest Calculation",
        filters=doc_filters,
        fields=[
            "loan_no",
            "client_name",
            "date",
            "transaction_type",
            "crdr",
            "debit",
            "credit",
            "loan_balance",
            "interest_with_rebate",
            "interest_without_rebate",
            "creation_date",
        ],
    )
    if interest_calculation_doc == []:
        frappe.throw(("Record does not exist"))

    final = pd.DataFrame([c.values() for c in interest_calculation_doc], index=None)
    final.columns = interest_calculation_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()

    df_subtotal = final.groupby(["Loan No", "Client Name"], as_index=False)[
        "Loan Balance", "Interest With Rebate", "Interest Without Rebate"
    ].sum()
    # Join dataframes
    df_new = pd.concat([final, df_subtotal], axis=0, ignore_index=True)
    # Sort
    df_new = df_new.sort_values(["Loan No", "Creation Date"])
    df_new.loc[
        (df_new["Loan No"].duplicated() & df_new["Client Name"].duplicated()),
        ["Loan No", "Client Name"],
    ] = ""
    df_new.loc[df_new["Date"].isnull(), "Transaction Type"] = "Closing Balance"
    df_new.drop("Creation Date", axis=1, inplace=True)
    df_new = df_new.rename(
        columns={
            "Crdr": "Cr/Dr",
            "Interest With Rebate": "Interest(With Rebate)",
            "Interest Without Rebate": "Interest(Without Rebate)",
        }
    )
    file_name = "interest_calculation_{}".format(frappe.utils.now_datetime())
    sheet_name = "Interest Calculation"
    return lms.download_file(
        dataframe=df_new,
        file_name=file_name,
        file_extention="xlsx",
        sheet_name=sheet_name,
    )
