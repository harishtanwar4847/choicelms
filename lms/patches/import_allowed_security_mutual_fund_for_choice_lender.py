import frappe


def execute():
    path = frappe.get_app_path(
        "lms", "patches", "imports", "allowed_security_for_mutual_fund.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Allowed Security", path, "Insert", console=True
    )
