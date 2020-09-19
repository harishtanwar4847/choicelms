import frappe
from frappe import _
import lms

@frappe.whitelist()
def my_loans():
    try:
        customer = lms.get_customer(frappe.session.user)

        loans = frappe.db.sql(""" select loan.total_collateral_value as loan_total_collateral_value,
            loan.name, mrgloan.total_collateral_value as loan_margin_shortfall_total_collateral_value, mrgloan.shortfall, 
            mrgloan.shortfall_percentage, mrgloan.shortfall_c from `tabLoan` as loan
            left join `tabLoan Margin Shortfall` as mrgloan
            on loan.name = mrgloan.loan where loan.customer = '{}' """.format(customer.name), as_dict = 1)

        return lms.generateResponse(message=_('Loan'), data={'loans': loans})

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)