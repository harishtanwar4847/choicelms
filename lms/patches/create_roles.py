import frappe


def execute():
    roles = [
        "Loan Customer",
        "Lender",
        "Spark Manager",
        "Spark Transaction Approver",
    ]
    for role in roles:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert()
    frappe.db.commit()
