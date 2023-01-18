import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Tutorial Screen", force=True)

    path = frappe.get_app_path("lms", "patches", "imports", "tutorial_screen.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Tutorial Screen", path, "Insert"
    )
