import frappe
from frappe import _
import lms

@frappe.whitelist()
def my_loan(frappe.session.user):
    try:
        customer = lms.get_customer(frappe.session.user)

        loan = frappe.db.get_all('Loan', filters = {'customer': customer})

        return lms.generateResponse(message=_('Loan'), data={'loan': loan})

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)