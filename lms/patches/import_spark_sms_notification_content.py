import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Spark SMS Notification")
    path = frappe.get_app_path("lms", "patches", "imports", "sms_notification1.csv")
    frappe.core.doctype.data_import.data_import.import_file(
            "Spark SMS Notification", path, "Insert"
        )