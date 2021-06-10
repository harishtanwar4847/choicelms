import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabAllowed Security`")
    frappe.db.commit()
    path = frappe.get_app_path("lms", "patches", "imports", "allowed_security.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Allowed Security", path, "Insert"
    )
