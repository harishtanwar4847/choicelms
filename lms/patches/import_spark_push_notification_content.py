import frappe


def execute():
    doc_exists = frappe.db.sql(
        "SELECT EXISTS(SELECT 1 FROM `tabSpark Push Notification`) as OUTPUT;",
        as_dict=True,
    )

    if not doc_exists[0].get("OUTPUT"):
        path = frappe.get_app_path(
            "lms", "patches", "imports", "spark_push_notification.csv"
        )
        frappe.core.doctype.data_import.data_import.import_file(
            "Spark Push Notification", path, "Insert"
        )
