import frappe


def execute():

    frappe.reload_doc("Lms", "DocType", "Loan")
    for loan in frappe.get_all("Loan", pluck="name"):
        try:
            loan = frappe.get_doc("Loan", loan)
            frappe.db.set_value(
                "Loan",
                loan.name,
                {
                    "is_default": 1,
                    "base_interest": 1.24,
                    "rebate_interest": 0.2,
                    "custom_base_interest": 1.24,
                    "custom_rebate_interest": 0.2,
                    "wef_date": frappe.utils.now_datetime().date(),
                },
                update_modified=False,
            )
        except:
            frappe.log_error(
                title="custom roi patch",
                message=frappe.get_traceback() + "\n\nLoan name :" + str(loan.name),
            )
