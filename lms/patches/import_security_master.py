import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabSecurity`")
    frappe.db.commit()
    path = frappe.get_app_path("lms", "patches", "imports", "security.csv")
    frappe.core.doctype.data_import.data_import.import_file("Security", path, "Insert")
