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

        data = {'loans': loans}
        data['total_outstanding'] = sum([i.outstanding for i in loans])
        data['total_overdraft_limit'] = sum([i.overdraft_limit for i in loans])
        data['total_total_collateral_value'] = sum([i.total_collateral_value for i in loans])
        data['total_margin_shortfall'] = sum([i.shortfall_c for i in loans])

        return lms.generateResponse(message=_('Loan'), data=data)

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)