from datetime import datetime

import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Loan")
    loans = frappe.get_all("Loan")
    curr_year = datetime.now().year
    curr_month = datetime.now().month
    for loan in loans:
        frappe.db.sql(
            "update `tabLoan` set base_interest_amount = (select sum(base_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_base = 0) where name = '{}'".format(
                loan.name, curr_year, curr_month, loan.name
            )
        )
        frappe.db.sql(
            "update `tabLoan` set rebate_interest_amount = (select sum(rebate_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_rebate = 0)  where name = '{}'".format(
                loan.name, curr_year, curr_month, loan.name
            )
        )
        frappe.db.sql(
            "update `tabLoan` set margin_shortfall_amount = IFNULL((select shortfall_c from `tabLoan Margin Shortfall` where loan = '{}' and status in ('Pending', 'Request Pending','Sell Triggered')),0.0) where name = '{}'".format(
                loan.name, loan.name
            )
        )
        frappe.db.commit()
