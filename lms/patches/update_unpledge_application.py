import frappe


def execute():
    unpledge_applications = frappe.get_all("Unpledge Application", fields=["*"])
    for unpledge_application in unpledge_applications:
        loan = frappe.get_doc("Loan", unpledge_application.loan)
        unpledge_application.customer_name = loan.customer_name
        pending_sell_request_id = frappe.db.get_value(
            "Sell Collateral Application", {"loan": unpledge_application.loan, "status": "Pending"}, "name"
        )
        if pending_sell_request_id:
            unpledge_application.pending_sell_request_id = pending_sell_request_id
        else:
            unpledge_application.pending_sell_request_id = ""
        unpledge_application.save()
    frappe.db.commit()
