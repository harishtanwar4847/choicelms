import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabSpark Push Notification`")
    frappe.db.commit()
    path = frappe.get_app_path(
        "lms", "patches", "imports", "Spark_Push_Notification.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Spark Push Notification", path, "Insert"
    )
