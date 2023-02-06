import frappe

import lms


def execute():
    frappe.reload_doc("Lms", "DocType", "Spark App Version", force=True)
    frappe.get_doc(
        {
            "doctype": "Spark App Version",
            "android_version": "1.0.8",
            "ios_version": "1.0.6",
            "play_store_link": "https://play.google.com/store/apps/details?id=com.sparktechnologies.sparkloans&hl=en",
            "app_store_link": "https://apps.apple.com/in/app/spark-loans/id1551799259?uo=4",
            "whats_new": "Force update",
            "release_date": frappe.utils.now_datetime().date(),
            "backend_version": lms.__version__,
            "is_live": 1,
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
