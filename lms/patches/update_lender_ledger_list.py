import frappe


def execute():
    # loans = frappe.get_all("Loan", fields=["*"])
    # loan_transactions = frappe.get_all("Loan Transaction", fields=["*"])
    lender_ledgers = frappe.get_all("Lender Ledger", fields=["*"])
    # for loan_transaction in loan_transactions:
    for lender_ledger in lender_ledgers:
            frappe.db.sql("""update `tabLender Ledger` set customer_name = (select customer_name from `tabLoan` where name = '{}')
        """.format(lender_ledger.loan))
            frappe.db.sql("""update `tabLender Ledger` set transaction_type = (select transaction_type from `tabLoan Transaction` where loan = '{}')
        """.format(lender_ledger.loan))
            # lender_ledger.transaction_type = loan_transaction.transaction_type
            # loan = frappe.get_doc("Loan", lender_ledger.loan)
            # lender_ledger.customer_name = loan.customer_name
            # lender_ledger.save()
    frappe.db.commit()
