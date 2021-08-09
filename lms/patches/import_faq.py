import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabFAQ`")
    frappe.db.sql("DELETE FROM `tabSeries` where name = %s", ("FAQ"))
    frappe.db.commit()
    path = frappe.get_app_path("lms", "patches", "imports", "faq.csv")
    frappe.core.doctype.data_import.data_import.import_file("FAQ", path, "Insert")
