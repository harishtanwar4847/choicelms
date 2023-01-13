import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Spark SMS Notification")
    frappe.db.sql("truncate table `tabSpark SMS Notification`")
    path = frappe.get_app_path(
        "lms", "patches", "imports", "spark_sms_notification_content.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Spark SMS Notification", path, "Insert", console=True
    )
