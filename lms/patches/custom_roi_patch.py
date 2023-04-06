import frappe


def execute():

    frappe.reload_doc("Lms", "DocType", "Loan")
    for loan in frappe.get_all("Loan", pluck="name"):
        try:
            loan = frappe.get_doc("Loan", loan)
            loan.is_default = 1
            loan.wef_date = frappe.utils.now_datetime().date()
            loan.save()
            frappe.db.commit()
        except:
            frappe.log_error(
                title="custom roi patch",
                message=frappe.get_traceback() + "\n\nLoan name :" + str(loan.name),
            )
