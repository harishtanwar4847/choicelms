import frappe
from frappe import _
import lms

@frappe.whitelist()
def list(mobile):
    try:
        user = lms.get_user(frappe.session.user)
        customer = frappe.db.get_value('Customer', {'username': user}, 'name')

        if not customer:
            return lms.generateResponse(message=_('User not registered.'))

        loan = frappe.db.get_value('Loan', {'customer': customer}, 'name')

        return lms.generateResponse(message=_('Loan'), data={'loan': loan})

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)