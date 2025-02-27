import frappe


def execute():
    las_settings = frappe.get_single("LAS Settings")

    las_settings.update(
        {
            "app_identification_hash_string": "Oy/3VpSHXSG",
            "cdsl_dpid": "66900",
            "cdsl_host": "https://web.cdslindia.com",
            "cdsl_password": "TH&#xh45",
            "cdsl_referrer": "https://www.cdslindia.com/index.html",
            "cdsl_user_id": "ANIL1234",
            "choice_business_unit": "JF",
            "choice_investor_id": "1",
            "choice_pan_api": "https://accounts.choicebroking.in/api/spark/getByDobAndPanNumDetails",
            "choice_securities_list_api": "https://api.choicebroking.in/api/middleware/GetClientHoldingDetails",
            "choice_ticket": "c3Bhcms=",
            "choice_user_id": "Spark",
            "enhancement_esign_download_signed_file_uri": "/esignForms/{file_id}/loan-enhancement-aggrement.pdf",
            "esign_download_signed_file_uri": "/esignForms/{file_id}/loan-aggrement.pdf",
            "esign_host": "https://esign.spark.loans/esign",
            "esign_request_uri": "/sparkEsignRequest?id={id}&xCoordinate={x}&yCoordinate={y}&pageNumber={page_number}",
            "esign_upload_file_uri": "/uploadFile",
            "jiffy_host": "https://jiffy.choicebroking.in",
            "jiffy_security_get_latest_price_uri": "/api/cm/ProfileMkt/MultipleTouchline",
            "jiffy_session_generator_uri": "/api/settings/GenKey",
            "pledge_setup_uri": "/PledgeAPIService/api/pledgesetup",
            "privacy_policy_document": None,
            "scheduler_from_time": 10,
            "scheduler_to_time": 21,
            "terms_of_use_document": None,
        }
    )
    # TODO: move terms of use and privacy document in public folder and add key for those in above dict
    las_settings.save()
    frappe.db.commit()
