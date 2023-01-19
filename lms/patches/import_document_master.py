import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Document Master", force=True)
    path = frappe.get_app_path("lms", "patches", "imports", "document_master.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Document Master", path, "Insert", console=True
    )
