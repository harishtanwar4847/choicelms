import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "LAS Settings", force=True)
    las_settings = frappe.get_single("LAS Settings")
    user_consent = frappe.get_all(
        "User Consent", filters={"consent": "Ckyc"}, pluck="name"
    )
    if user_consent:
        frappe.delete_doc("User Consent", user_consent)
    frappe.delete_doc_if_exists("Consent", "Ckyc")

    if frappe.utils.get_url() == "https://spark.loans":
        las_settings.ckyc_search_api = "https://kyc.spark.loans/api/ckyc/search"
        las_settings.ckyc_download_api = "https://kyc.spark.loans/api/ckyc/download"
    else:
        las_settings.ckyc_search_api = "https://uatkyc.spark.loans/api/ckyc/search"
        las_settings.ckyc_download_api = "https://uatkyc.spark.loans/api/ckyc/download"

    frappe.get_doc(
        {
            "doctype": "Consent",
            "name": "Ckyc",
            "consent": "I hereby give my consent for storing the information received from C-KYC Registry or to be updated as and when required. I declare that the details furnished above are true and correct to the best of my knowledge and belief and I undertake to inform you of any changes therein, immediately. In case any of the above information is found to be false or untrue or misleading or misrepresenting, I am aware that I may be held liable for it.",
        }
    ).insert(ignore_permissions=True)
    las_settings.save(ignore_permissions=True)
    frappe.db.commit()
