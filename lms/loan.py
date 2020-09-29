import frappe
from frappe import _
import lms

@frappe.whitelist()
def my_loans():
    try:
        customer = lms.get_customer(frappe.session.user)

        loans = frappe.db.sql("""select 
            loan.total_collateral_value, loan.name, loan.sanctioned_limit, loan.drawing_power,

            if (loan.total_collateral_value * loan.allowable_ltv / 100 > loan.sanctioned_limit, 1, 0) as top_up_available,

            if (loan.total_collateral_value * loan.allowable_ltv / 100 > loan.sanctioned_limit, 
            loan.total_collateral_value * loan.allowable_ltv / 100 - loan.sanctioned_limit, 0.0) as top_up_amount,

            IFNULL(mrgloan.shortfall_percentage, 0.0) as shortfall_percentage, 
            IFNULL(mrgloan.shortfall_c, 0.0) as shortfall_c,
            IFNULL(mrgloan.shortfall, 0.0) as shortfall,

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
        data['total_sanctioned_limit'] = sum([i.sanctioned_limit for i in loans])
        data['total_drawing_power'] = sum([i.drawing_power for i in loans])
        data['total_total_collateral_value'] = sum([i.total_collateral_value for i in loans])
        data['total_margin_shortfall'] = sum([i.shortfall_c if i.shortfall_c else 0.0 for i in loans])

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
            "pledgor_boid":pledgor_boid,
            "pledgee_boid":pledgee_boid,
            "prf_number":prf_number,
            "isin":item.isin,
            'quantity': item.pledged_quantity,
            'psn': item.psn,
            'error_code': item.error_code
        })
        loan_collateral.insert(ignore_permissions=True)