# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
from datetime import datetime

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
                )
            )
    interest_calculation_list.sort(
        key=lambda item: (item["loan_no"], item["date"]), reverse=True
    )
    for i in interest_calculation_list:
        frappe.get_doc(i).insert(ignore_permissions=True)
        frappe.db.commit()


@frappe.whitelist()
def interest_calculation_enqueue():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            frappe.enqueue(
                method="lms.lms.doctype.interest_calculation.interest_calculation.interest_calculation",
                queue="long",
                loan=loan,
            )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Interest Calculation"),
        )


@frappe.whitelist()
def excel_generator(doc_filters):
    print(doc_filters)
    interest_calculation_doc = frappe.get_all(
        "Interest Calculation",
        filters=doc_filters,
        fields=[
            "loan_no",
            "client_name",
            "date",
            "transaction_type",
            "crdr",
            "creation_date",
            "debit",
            "credit",
            "loan_balance",
            "interest_with_rebate",
            "interest_without_rebate",
        ],
    )
    if interest_calculation_doc == []:
        frappe.throw(("Record does not exist"))

    final = pd.DataFrame([c.values() for c in interest_calculation_doc], index=None)
    final.columns = interest_calculation_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    # report = final.sum(numeric_only=True)
    # report = final.iloc[:, 3:8].sum()
    # final.loc["Total"] = report
    final.fillna("")
    # final.set_index(['loan_no','client_name','pan_no','sanctioned_amount','pledged_value','drawing_power','loan_balance','adp_shortfall','roi_','client_demat_acc','customer_contact_no','loan_expiry_date','dpd'])
    # report = final.groupby(['']).apply(lambda sub_df:  sub_df.pivot_table(index=['customer','customer_name','transaction_type'], values=['amount'],aggfunc=np.sum, margins=True,margins_name= 'TOTAL'))
    # report.loc[('', 'Grand Total','',''), :] = report[report.index.get_level_values(1) != 'TOTAL'].sum()
    # report=report.reset_index(level=0,drop=True)
    # final
    # report=report.reset_index(level=0,drop=True)
    final.to_excel("client_summary.xlsx", index=False)
