import frappe

import lms


def execute():
    try:
        frappe.reload_doc("Lms", "DocType", "LAS Settings", force=True)
        las_settings = frappe.get_single("LAS Settings")
        if frappe.utils.get_url() == "https://spark.loans":
            las_settings.penny_drop_api = (
                "https://api.choiceconnect.in/connect/api/penny-drop/validate-bank"
            )
            las_settings.penny_secret_key = (
                "&kGh#jqCfMESLVFH5@xI7yw^HaRpgDqUCR56dttyS)J7cPGJ9pxB6c*BFunH*9ZM"
            )
        else:
            las_settings.penny_drop_api = (
                "https://apidev.choiceconnect.in/connect/api/penny-drop/validate-bank"
            )
            las_settings.penny_secret_key = (
                "&kGh#jqCfMESLVFH5@xI7yw^HaRpgDqUCR56dttyS)J7cPGJ9pxB6c*BFunH*9ZM"
            )
        las_settings.pennydrop_days_passed = 90
        las_settings.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error()
