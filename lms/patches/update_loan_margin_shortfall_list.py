import frappe


def execute():
    loans_margin_shortfalls = frappe.get_all("Loan Margin Shortfall", fields=["*"])
    for loans_margin_shortfall in loans_margin_shortfalls:
        frappe.db.sql(
            """
            update `tabLoan Margin Shortfall` set customer_name = (select customer_name from `tabLoan` where name = '{}') where name = '{}'
            """.format(
                loans_margin_shortfall.loan, loans_margin_shortfall.name
            )
        )
        frappe.db.commit()
