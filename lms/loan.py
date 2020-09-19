import frappe
from frappe import _
import lms

@frappe.whitelist()
def list(mobile):
    try:
        if not mobile:
			raise lms.ValidationError(_('Mobile is required.'))

        if len(mobile) != 10 or not mobile.isdigit():
			raise lms.ValidationError(_('Enter valid Mobile.'))

        customer = frappe.db.get_value('Customer', {'user': mobile}, 'name')

        if not customer:
            return lms.generateResponse(message=_('User not registered.'))

        loan = frappe.db.get_value('Loan', {'customer': customer}, 'name')

        if not loan:
            return lms.generateResponse(message=_('Loan not created for this user.'))
        else:    
            return lms.generateResponse(message=_('Loan'))

    except (lms.ValidationError, lms.ServerError) as e:
        return lms.generateResponse(status=e.http_status_code, message=str(e))
    except Exception as e:
        return lms.generateResponse(is_success=False, error=e)    


