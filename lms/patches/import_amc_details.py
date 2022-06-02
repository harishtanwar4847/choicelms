import frappe


def execute():
    frappe.db.sql("truncate `tabAMC Master`")
    frappe.db.commit()
    path = frappe.get_app_path("lms", "patches", "imports", "amc_master_details.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "AMC Master", path, "Insert"
    )
