import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Proof of Address Master", force=True)
    path = frappe.get_app_path(
        "lms", "patches", "imports", "proof_of_address_master.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Proof of Address Master", path, "Insert", console=True
    )
