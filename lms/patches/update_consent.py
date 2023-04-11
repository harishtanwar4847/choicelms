import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabConsent`")

    frappe.reload_doc("Lms", "DocType", "Consent")
    path = frappe.get_app_path("lms", "patches", "imports", "consent_re_ckyc.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Consent", path, "Insert", console=True
    )
