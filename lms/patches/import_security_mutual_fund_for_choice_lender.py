import frappe


def execute():
    try:
        path = frappe.get_app_path(
            "lms", "patches", "imports", "security_for_mutual_fund.csv"
        )
        frappe.core.doctype.data_import.data_import.import_file(
            "Security", path, "Insert"
        )
    except Exception:
        frappe.log_error(title="security_for_mutual_fund")
