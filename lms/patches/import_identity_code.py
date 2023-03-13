import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Identity Code", force=True)

    path = frappe.get_app_path("lms", "patches", "imports", "identity_code.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Identity Code", path, "Insert", console=True
    )
