import frappe


def execute():
    # workflow states
    states = [
        "Pending",
        "Approved",
        "Rejected",
        "Pledge Approved",
        "Esign Done",
        "Ready for Approval",
        "Esign Pending",
        "Waiting to be pledged",
        "Executing pledge",
        "Pledge executed",
        "Pledge accepted by Lender",
    ]

    for state in states:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc(
                {"doctype": "Workflow State", "workflow_state_name": state}
            ).insert()
    frappe.db.commit()

    # workflow actions
    actions = [
        "Pending pledge",
        "Esign",
        "Send for Approval",
        "Review",
        "Reject",
        "Approve",
    ]

    for action in actions:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc(
                {"doctype": "Workflow Action Master", "workflow_action_name": action}
            ).insert()
    frappe.db.commit()

    # workflows
    frappe.db.sql("TRUNCATE `tabWorkflow`")
    frappe.db.sql("TRUNCATE `tabWorkflow Document State`")
    frappe.db.sql("TRUNCATE `tabWorkflow Transition`")
    frappe.db.commit()
    path = frappe.get_app_path("lms", "patches", "imports", "workflow.csv")
    frappe.core.doctype.data_import.data_import.import_file("Workflow", path, "Insert")
