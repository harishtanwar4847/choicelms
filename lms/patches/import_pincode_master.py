import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Pincode Master", force=True)
    path = frappe.get_app_path("lms", "patches", "imports", "pincode_master.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Pincode Master", path, "Insert", console=True
    )
