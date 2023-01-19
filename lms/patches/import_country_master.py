import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Country Master", force=True)
    path = frappe.get_app_path("lms", "patches", "imports", "country_master.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Country Master", path, "Insert", console=True
    )
