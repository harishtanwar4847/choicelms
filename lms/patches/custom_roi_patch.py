import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Loan")
    for loan in frappe.get_all("Loan", pluck="name"):
        loan = frappe.get_doc("Loan", loan)
        loan.is_default = 1
        loan.wef_date = frappe.utils.now_datetime().date()
        loan.save()
        frappe.db.commit()
