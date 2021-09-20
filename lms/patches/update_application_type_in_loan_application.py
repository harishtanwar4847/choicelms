import frappe

import lms


def execute():
    all_loan_applications = frappe.get_all("Loan Application")
    for la in all_loan_applications:
        try:
            la = frappe.get_doc("Loan Application", la)
            if not la.loan:
                la.application_type = "New Loan"
            elif la.loan and not la.loan_margin_shortfall:
                la.application_type = "Increase Loan"
            elif la.loan and la.loan_margin_shortfall:
                la.application_type = "Margin Shortfall"
            la.save(ignore_permissions=True)
            frappe.db.commit()
        except:
            pass
