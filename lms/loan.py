import frappe
from frappe import _
import lms

@frappe.whitelist()
def my_loans():
    try:
        customer = lms.get_customer(frappe.session.user)

        loans = frappe.db.sql("""select 
            loan.total_collateral_value, loan.name, mrgloan.shortfall, loan.overdraft_limit,
            mrgloan.shortfall_percentage, mrgloan.shortfall_c,
            SUM(COALESCE(CASE WHEN loantx.record_type = 'DR' THEN loantx.transaction_amount END,0)) 
			- SUM(COALESCE(CASE WHEN loantx.record_type = 'CR' THEN loantx.transaction_amount END,0)) outstanding 
            from `tabLoan` as loan
            left join `tabLoan Margin Shortfall` as mrgloan
            on loan.name = mrgloan.loan 
            left join `tabLoan Transaction` as loantx
            on loan.name = loantx.loan
            where loan.customer = '{}' group by loantx.loan """.format(customer.name), as_dict = 1)

        return lms.generateResponse(message=_('Loan'), data={'loans': loans})

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)