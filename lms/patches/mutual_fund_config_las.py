import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "LAS Settings")
    las_settings = frappe.get_single("LAS Settings")
    if frappe.utils.get_url() == "https://spark.loans":
        las_settings.lien_marking_api = (
            "https://mycams.camsonline.com/lamfapi/pgLienmarking.aspx"
        )
        las_settings.lien_initiate_api = (
            "https://mycams.camsonline.com/lamfapi/trxn/v1/initiatelien"
        )
        las_settings.invoke_api = "https://mycams.camsonline.com/lamfapi/trxn/v1/invoc"
        las_settings.revoke_api = "https://mycams.camsonline.com/lamfapi/trxn/v1/revoc"
        las_settings.lien_allowed_scheme_update_api = (
            "https://mycams.camsonline.com/lamfapi/trxn/v1/lienscheme"
        )

    else:
        las_settings.lien_marking_api = (
            "https://mycamsuat.camsonline.com/lamfapi/pgLienmarking.aspx"
        )
        las_settings.lien_initiate_api = (
            "https://mycamsuat.camsonline.com/lamfapi/trxn/v1/initiatelien"
        )
        las_settings.invoke_api = (
            "https://mycamsuat.camsonline.com/lamfapi/trxn/v1/invoc"
        )
        las_settings.revoke_api = (
            "https://mycamsuat.camsonline.com/lamfapi/trxn/v1/revoc"
        )
        las_settings.lien_allowed_scheme_update_api = (
            "https://mycamsuat.camsonline.com/lamfapi/trxn/v1/lienscheme"
        )

    las_settings.investica_api = "https://api.choiceindia.com/api/bo/Scheme/SchemeNav"
    las_settings.encryption_key = "TkVJTEhobWFj"
    las_settings.decryption_key = "SExJRU5obWFj"
    las_settings.secret_key = "HakUx7K9JlfUBE/eL+YES1MAW1EscwI+NOgoIaXVwGU="
    las_settings.hmac_key = "TEFNRi1UQ0ZJTlBMVERobWFj"
    las_settings.iv = "globalaesvectors"
    las_settings.client_id = "LAMF-TCFINPLTD"
    las_settings.client_name = "Choice Finserv Pvt Ltd"
    las_settings.bank_reference_no = "1001"
    las_settings.bank_name = "Choice Finserv Pvt Ltd"
    las_settings.shares_ltv = 50
    las_settings.mf_equity_ltv = 50
    las_settings.mf_debt_ltv = 80

    las_settings.save(ignore_permissions=True)
    frappe.db.commit()
