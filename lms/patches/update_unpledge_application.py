import frappe


def execute():
    unpledge_applications = frappe.get_all("Unpledge Application", fields=["*"])
    for unpledge_application in unpledge_applications:
        # frappe.db.sql("""
        # update `tabUnpledge Application` set customer_name = (select customer_name from `tabLoan` where name = '{}')
        # """.format(unpledge_application.loan))
        frappe.db.sql(
            """
            update `tabUnpledge Application` set pending_sell_request_id = (select name from `tabSell Collateral Application` where status = "Pending" and loan = '{}')
            """.format(unpledge_application.loan)
        )
    frappe.db.commit()
