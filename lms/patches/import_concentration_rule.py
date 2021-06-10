import frappe


def execute():
    path = frappe.get_app_path("lms", "patches", "imports", "concentration_rule.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Concentration Rule", path, "Insert"
    )
