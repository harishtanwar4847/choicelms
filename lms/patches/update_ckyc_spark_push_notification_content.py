import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Spark Push Notification", force=True)

    frappe.db.sql("truncate table `tabSpark Push Notification`")

    path = frappe.get_app_path(
        "lms", "patches", "imports", "update_ckyc_spark_push_notification_content.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Spark Push Notification", path, "Insert"
    )
