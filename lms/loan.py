import frappe
from frappe import _

@frappe.whitelist()
def list(phone):
    customer = frappe.db.get_value('Customer', {'user': phone}, 'name')

    loan = frappe.db.get_value('Loan', {'customer': customer}, 'name')

    return loan
