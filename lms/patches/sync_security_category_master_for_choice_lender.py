import frappe


def execute():
    security_category_master = frappe.reload_doc("Lms", "DocType", "Security Category")

    doc_exists = frappe.db.sql(
        "SELECT EXISTS(SELECT 1 FROM `tabSecurity Category`) as OUTPUT;",
        as_dict=True,
    )

    if security_category_master and not doc_exists[0].get("OUTPUT"):
        # path = frappe.get_app_path(
        #     "lms", "patches", "imports", "spark_push_notification.csv"
        # )
        # frappe.core.doctype.data_import.data_import.import_file(
        #     "Spark Push Notification", path, "Insert"
        # )
        distinct_securities = ""
