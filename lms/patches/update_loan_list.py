import frappe
from lms.lms.doctype.loan.loan import Loan
from datetime import datetime


def execute():
    loans = frappe.get_all("Loan", fields=["*"])
    curr_year = datetime.now().year
    curr_month = datetime.now().month
    for loan in loans:
        loan.base_interest_amount = frappe.db.sql(
            "select sum(base_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_base = 0".format(
                loan.name, curr_year, curr_month
            ),
            as_dict=1,
        )[0]["amount"]
        loan.rebate_interest_amount = frappe.db.sql(
            "select sum(rebate_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_rebate = 0".format(
                loan.name,curr_year, curr_month
            ),
            as_dict=1,
        )[0]["amount"]

        loan_margin_shortfall = Loan.get_margin_shortfall()
        loan.margin_shortfall_amount = loan_margin_shortfall.shortfall_c
        loan.save()
    frappe.db.commit()
