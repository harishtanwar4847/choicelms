import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabInterest Configuration`")
    frappe.db.commit()
    path = frappe.get_app_path(
        "lms", "patches", "imports", "interest_configuration.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Interest Configuration", path, "Insert"
    )
