import frappe


def execute():
    path = frappe.get_app_path("lms", "patches", "imports", "security.csv")
    frappe.core.doctype.data_import.data_import.import_file("Security", path, "Insert")
