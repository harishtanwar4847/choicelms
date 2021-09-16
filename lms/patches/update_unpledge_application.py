import frappe


def execute():
    unpledge_applications = frappe.get_all("Unpledge Application", fields=["*"])
    for unpledge_application in unpledge_applications:
        cust_name = frappe.get_doc("Loan Customer", unpledge_application.customer)
        loan = frappe.get_doc("Loan", unpledge_application.loan)
        allowable_value = loan.max_unpledge_amount()
        frappe.db.sql(
            """
            update `tabUnpledge Application` set pending_sell_request_id = (select name from `tabSell Collateral Application` where status = "Pending" and loan = '{}'), customer_name = '{}', max_unpledge_amount = {} where name = '{}'
            """.format(
                unpledge_application.loan,
                cust_name.full_name,
                allowable_value["maximum_unpledge_amount"],
                unpledge_application.name,
            )
        )
        frappe.db.commit()
