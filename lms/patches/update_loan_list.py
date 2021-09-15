import frappe
from datetime import datetime

def execute():
    loans = frappe.get_all("Loan")
    curr_year = datetime.now().year
    curr_month = datetime.now().month
    for loan in loans:  
        frappe.db.sql(
            "update `tabLoan` set base_interest_amount =  (select sum(base_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_base = 0)".format(
                loan.name,curr_year, curr_month),
        )
        frappe.db.sql(
            "update `tabLoan` set rebate_interest_amount =  (select sum(rebate_amount) as amount from `tabVirtual Interest` where loan = '{}' and DATE_FORMAT(time, '%Y') = {} and DATE_FORMAT(time, '%m') = {} and is_booked_for_rebate = 0)".format(
                loan.name,curr_year, curr_month)
        )
        frappe.db.sql(
            "update `tabLoan` set margin_shortfall_amount =  (select shortfall_c from `tabLoan Margin Shortfall` where loan = '{}' and status in ('Pending', 'Request Pending','Sell Triggered'))".format(loan.name))
    frappe.db.commit()
