import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "State Master")

    path = frappe.get_app_path("lms", "patches", "imports", "state_master.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "State Master", path, "Insert", console=True
    )
