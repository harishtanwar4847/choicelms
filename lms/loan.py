import frappe
from frappe import _
import lms

@frappe.whitelist()
def my_loans():
    try:
        customer = lms.get_customer(frappe.session.user)

        loans = frappe.db.sql("""select 
            loan.total_collateral_value, loan.name, mrgloan.shortfall, loan.drawing_power,
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
        data['total_drawing_power'] = sum([i.drawing_power for i in loans])
        data['total_total_collateral_value'] = sum([i.total_collateral_value for i in loans])
        data['total_margin_shortfall'] = sum([i.shortfall_c for i in loans])

        return lms.generateResponse(message=_('Loan'), data=data)

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)

def create_loan_collateral(loan_name, pledgor_boid, pledgee_boid, prf_number, items):
    for item in items:
        loan_collateral = frappe.get_doc({
            "doctype":"Loan Collateral",
            "loan":loan_name,
            "request_type":"Pledge",
            "pledgor_boid":pledgor_boid,
            "pledgee_boid":pledgee_boid,
            "request_identifier":prf_number,
            "isin":item.isin,
            "quantity": item.pledged_quantity,
            "psn": item.psn,
            "error_code": item.error_code,
            "is_success": item.psn and not item.error_code
        })
        loan_collateral.insert(ignore_permissions=True)