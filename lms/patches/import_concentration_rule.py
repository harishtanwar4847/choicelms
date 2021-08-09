import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabConcentration Rule`")
    frappe.db.commit()
    path = frappe.get_app_path("lms", "patches", "imports", "concentration_rule.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Concentration Rule", path, "Insert"
    )
