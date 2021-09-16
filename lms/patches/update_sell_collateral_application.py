import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Sell Collateral Application")
    sell_collateral_applications = frappe.get_all(
        "Sell Collateral Application", fields=["*"]
    )
    for sell_collateral_application in sell_collateral_applications:
        cust_name = frappe.get_doc(
            "Loan Customer", sell_collateral_application.customer
        )
        if cust_name:
            frappe.db.sql(
                """
                update `tabSell Collateral Application` set pending_unpledge_request_id = (select name from `tabUnpledge Application` where status = "Pending" and loan = '{}'), customer_name = '{}'  where name = '{}'
                """.format(
                    sell_collateral_application.loan,
                    cust_name.full_name,
                    sell_collateral_application.name,
                )
            )
            frappe.db.commit()
