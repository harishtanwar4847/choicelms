import frappe


def execute():
    frappe.db.sql("truncate `tabAMC Details`")
    frappe.db.commit()
    path = frappe.get_app_path("lms", "patches", "imports", "amc_code_details.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "AMC Details", path, "Insert"
    )
