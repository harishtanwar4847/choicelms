import frappe


def execute():
    virtual_interests = frappe.get_all("Virtual Interest", fields=["*"])
    for virtual_interest in virtual_interests:
        loan = frappe.get_doc("Loan", virtual_interest.loan)
        virtual_interest.customer_name = loan.customer_name
        virtual_interest.save()
    frappe.db.commit()
