import frappe
from frappe import _
import lms

@frappe.whitelist()
def my_loan(frappe.session.user):
    try:
        user = lms.get_user(frappe.session.user)
        customer = lms.get_customer(user)

        if not customer:
            return lms.generateResponse(message=_('User not registered.'))

        loan = frappe.db.get_value('Loan', {'customer': customer}, 'name')

        return lms.generateResponse(message=_('Loan'), data={'loan': loan})

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)