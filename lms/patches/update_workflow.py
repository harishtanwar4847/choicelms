import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Workflow")

    frappe.db.sql("TRUNCATE `tabWorkflow`")
    frappe.db.sql("TRUNCATE `tabWorkflow Document State`")
    frappe.db.sql("TRUNCATE `tabWorkflow Transition`")
    frappe.db.commit()

    path = frappe.get_app_path("lms", "patches", "imports", "workflow1.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Workflow", path, "Insert", console=True
    )
