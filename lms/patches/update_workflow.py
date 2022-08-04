import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Workflow")
    path = frappe.get_app_path("lms", "patches", "imports", "workflow1.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Workflow", path, "Update", console=True
    )
