import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "LAS Settings")
    las_settings = frappe.get_single("LAS Settings")

    las_settings.update(
        {
            "pennydrop_create_contact": "https://api.razorpay.com/v1/contacts",
            "pennydrop_create_fund_account": "https://api.razorpay.com/v1/fund_accounts",
            "settlement_recon_api": "https://api.razorpay.com/v1/settlements/recon/combined",
            "pennydrop_create_fund_account_validation": "https://api.razorpay.com/v1/fund_accounts/validations",
            "pennydrop_create_fund_account_validation_id": "https://api.razorpay.com/v1/fund_accounts/validations",
        }
    )
    las_settings.save()
    frappe.db.commit()
