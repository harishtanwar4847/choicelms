import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "LAS Settings")
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": "support-spark@atriina.com",
            "first_name": "Razorpay",
            "last_name": "User",
            "username": "1234567890",
            "phone": "1234567890",
            "mobile_no": "1234567890",
            "send_welcome_email": 0,
            "new_password": "rzp@choice123",
            "roles": [{"doctype": "Has Role", "role": "Razorpay User"}],
        }
    ).insert(ignore_permissions=True)

    las_settings = frappe.get_single("LAS Settings")
    if frappe.utils.get_url() == "https://spark.loans":
        las_settings.razorpay_key_secret = (
            "rzp_live_55JW5NYsUIguyM:J1px4sH9cxxdbY1SfBgIOly0"
        )
    else:
        las_settings.razorpay_key_secret = (
            "rzp_test_Y6V9MAUGbQlOrW:vEnHHmtHpxZvYwDOEfDZmmPZ"
        )
    las_settings.save(ignore_permissions=True)
    frappe.db.commit()
