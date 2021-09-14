import frappe


def execute():
    loans_margin_shortfalls = frappe.get_all("Loan Margin Shortfall", fields=["*"])
    for loans_margin_shortfall in loans_margin_shortfalls:
        loan = frappe.get_doc("Loan", loans_margin_shortfall.loan)
        loans_margin_shortfall.customer_name = loan.customer_name
        loans_margin_shortfall.save()
    frappe.db.commit()
