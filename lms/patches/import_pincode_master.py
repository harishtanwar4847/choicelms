import frappe


def execute():
    path = frappe.get_app_path("lms", "patches", "imports", "pincode_master.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Pincode Master", path, "Insert", console=True
    )
