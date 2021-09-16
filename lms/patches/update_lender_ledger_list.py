import frappe


def execute():
    lender_ledgers = frappe.get_all("Lender Ledger", fields=["*"])
    for lender_ledger in lender_ledgers:
        frappe.db.sql(
            """update `tabLender Ledger` set customer_name = (select customer_name from `tabLoan` where name = '{}')  where name = '{}'
        """.format(
                lender_ledger.loan, lender_ledger.name
            )
        )
        frappe.db.sql(
            """update `tabLender Ledger` set transaction_type = (select transaction_type from `tabLoan Transaction` where name = '{}') where name = '{}'
        """.format(
                lender_ledger.loan_transaction, lender_ledger.name
            )
        )
        frappe.db.commit()
