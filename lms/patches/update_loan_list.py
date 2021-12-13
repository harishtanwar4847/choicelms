from datetime import datetime

import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Loan")
    loans = frappe.get_all("Loan")
    curr_year = datetime.now().year
    curr_month = datetime.now().month
    curr_date = frappe.utils.now_datetime().isoformat()
    for loan in loans:
        frappe.db.sql(
            "update `tabLoan` set base_interest_amount = IFNULL((select sum(base_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_base = 0),0.0) where name = '{}'".format(
                loan.name, curr_year, curr_month, loan.name
            )
        )
        frappe.db.sql(
            "update `tabLoan` set rebate_interest_amount = IFNULL((select sum(rebate_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_rebate = 0),0.0)  where name = '{}'".format(
                loan.name, curr_year, curr_month, loan.name
            )
        )
        frappe.db.sql(
            "update `tabLoan` set margin_shortfall_amount = IFNULL((select shortfall_c from `tabLoan Margin Shortfall` where loan = '{}' and status in ('Pending', 'Request Pending','Sell Triggered')),0.0) where name = '{}'".format(
                loan.name, loan.name
            )
        )
        # frappe.db.sql(
        #     "update `tabLoan` set interest_due = IFNULL((select unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Interest' and unpaid_interest > 0 order by time desc limit 1),0.0) where name = '{}'".format(
        #         loan.name, loan.name
        #     )
        # )
        # frappe.db.sql(
        #     "update `tabLoan` set interest_overdue = IFNULL((select sum(unpaid_interest) as unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type in ('Interest', 'Additional Interest') and unpaid_interest >0),0.0) where name = '{}'".format(
        #         loan.name, loan.name
        #     )
        # )
        # frappe.db.sql(
        #     "update `tabLoan` set penal_interest_charges = IFNULL((select sum(unpaid_interest) as unpaid_interest from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Penal Interest' and unpaid_interest >0),0.0) where name = '{}'".format(
        #         loan.name, loan.name
        #     )
        # )
        frappe.db.sql(
            "update `tabLoan` set total_interest_incl_penal_due = IFNULL((select sum(unpaid_interest) as total_amount from `tabLoan Transaction` where loan = '{}' and transaction_type in ('Interest', 'Additional Interest', 'Penal Interest') and unpaid_interest >0),0.0) where name = '{}'".format(
                loan.name, loan.name
            )
        )
        frappe.db.sql(
            "update `tabLoan` set day_past_due = IFNULL((select DATEDIFF('{}', time) as dpd from `tabLoan Transaction` where loan = '{}' and transaction_type = 'Interest' and unpaid_interest >0 order by creation asc),0) where name = '{}'".format(
                curr_date, loan.name, loan.name
            )
        )
        frappe.db.commit()
