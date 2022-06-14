import frappe


def execute():
    path = frappe.get_app_path("lms", "patches", "imports", "related_person_type.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Related Person Type", path, "Insert", console=True
    )
