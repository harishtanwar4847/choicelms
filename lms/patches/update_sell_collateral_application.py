import frappe


def execute():
    sell_collateral_applications = frappe.get_all("Sell Collateral Application", fields=["*"])
    for sell_collateral_application in sell_collateral_applications:
        loan = frappe.get_doc("Loan", sell_collateral_application.loan)
        sell_collateral_application.customer_name = loan.customer_name
        pending_unpledge_request_id = frappe.db.get_value(
            "Unpledge Application", {"loan": sell_collateral_application.loan, "status": "Pending"}, "name"
        )
        if pending_unpledge_request_id:
            sell_collateral_application.pending_unpledge_request_id = pending_unpledge_request_id
        else:
            sell_collateral_application.pending_unpledge_request_id = ""
        sell_collateral_application.save()
    frappe.db.commit()
