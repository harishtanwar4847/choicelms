import frappe


def execute():
    frappe.reload_doc("Lms", "Doctype", "AMC Master")

    doc_exists = frappe.db.sql(
        "SELECT EXISTS(SELECT 1 FROM `tabAMC Master`) as OUTPUT;",
        as_dict=True,
    )
    if doc_exists[0]["OUTPUT"]:
        frappe.db.sql("truncate `tabAMC Master`")
    # frappe.db.commit()

    path = frappe.get_app_path("lms", "patches", "imports", "amc_master_details.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "AMC Master", path, "Insert"
    )
