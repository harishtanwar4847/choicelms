import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "District Master")
    path = frappe.get_app_path("lms", "patches", "imports", "district_master.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "District Master", path, "Insert", console=True
    )
