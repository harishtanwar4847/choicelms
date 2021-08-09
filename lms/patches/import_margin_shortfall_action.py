import frappe


def execute():
    frappe.db.sql("truncate `tabMargin Shortfall Action`")
    frappe.db.commit()
    path = frappe.get_app_path(
        "lms", "patches", "imports", "margin_shortfall_action.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Margin Shortfall Action", path, "Insert"
    )
