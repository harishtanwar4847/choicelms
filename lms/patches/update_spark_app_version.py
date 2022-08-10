import frappe

import lms


def execute():
    frappe.reload_doc("Lms", "DocType", "Spark App Version")
    frappe.get_doc(
        {
            "doctype": "Spark App Version",
            "android_version": "1.0.8",
            "ios_version": "1.0.6",
            "whats_new": "Force update",
            "release_date": frappe.utils.now_datetime().date(),
            "backend_version": lms.__version__,
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
