# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InterestCalculation(Document):
    pass


def interest_calculation(loan):
    interest_calculation_list = []
    transactions = frappe.get_all(
        "Loan Transaction",
        filters={"loan": loan.name, "status": "Approved"},
        fields=["*"],
    )
    interests = frappe.get_all(
        "Virtual Interest", filters={"loan": loan.name}, fields=["*"]
    )
    for transaction in transactions:
        print("Transaction", transaction.name)
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
                date=transaction.time,
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
        rebate = interest.base_amount + interest.rebate_interest
        interest_calculation_list.append(
            dict(
                doctype="Interest Calculation",
                loan_no=loan.name,
                client_name=loan.customer_name,
                date=interest.time,
                transaction_type="-",
                crdr="-",
                credit="-",
                debit="-",
                loan_balance=interest.loan_balance,
                interest_with_rebate=rebate,
                interest_without_rebate=interest.base_amount,
            )
        )
    interest_calculation_list.sort(key=lambda item: (item["loan_no"]), reverse=True)
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
            # interest_calculation = frappe.get_doc(
            #     dict(
            #         doctype = "Interest Calculation",
            #         loan_no = loan.name,
            #         client_name = loan.customer_name,
            #         date = interest.creation.date(),
            #         transaction_type = transaction_type,
            #         crdr = crdr,
            #         debit = debit,
            #         credit = credit,
            #         loan_balance = loan.balance,
            #         interest_with_rebate = rebate,
            #         interest_without_rebate = interest.base_amount
            #     ),
            # ).insert(ignore_permissions=True)
            # frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Interest Calculation"),
        )
