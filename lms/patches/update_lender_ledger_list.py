import frappe


def execute():
    loans = frappe.get_all("Loan", fields=["*"])
    loan_transactions = frappe.get_all("Loan Transaction", fields=["*"])
    lender_ledgers = frappe.get_all("Lender Ledger", fields=["*"])
    for loan_transaction in loan_transactions:
        for lender_ledger in lender_ledgers:
            lender_ledger.transaction_type = loan_transaction.transaction_type
            loan = frappe.get_doc("Loan", lender_ledger.loan)
            lender_ledger.customer_name = loan.customer_name
            lender_ledger.save()
    frappe.db.commit()
