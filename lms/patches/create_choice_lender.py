from datetime import datetime

import frappe


def execute():
    data = {
        "full_name": "Choice Finserv",
        "pan_id": None,
        "demat_account_number": "1206690000284106",
        "interest_percentage_sharing": 0.84,
        "default_interest": 4.0,
        "account_renewal_charges": 0.5,
        "security_selling_share": 0.5,
        "cic_charges": 100.0,
        "gst_id": None,
        "registered_date": "2020-09-21",
        "rate_of_interest": 1.25,
        "transaction_charges_per_request": 100.0,
        "rebait_threshold": "7",
        "default_interest_threshold": "15",
        "is_active": 1,
        "agreement_template": "/assets/lms/agreement-templates/loan-agreement.html",
        "total_pages": 20,
        "coordinates": "370,610",
        "esign_page": 20,
        "enhancement_agreement_template": "/assets/lms/agreement-templates/loan-agreement.html",
        "enhancement_total_pages": 20,
        "enhancement_coordinates": "370,575",
        "enhancement_esign_page": 20,
        "lender_processing_fees_type": "Percentage",
        "stamp_duty_type": "Percentage",
        "documentation_charge_type": "Fix",
        "mortgage_charge_type": "Percentage",
        "lender_processing_fees": 1.0,
        "stamp_duty": 0.1,
        "documentation_charges": 10.0,
        "mortgage_charges": 0.1,
        "lender_processing_fees_sharing_type": "Percentage",
        "stamp_duty_sharing_type": "Percentage",
        "documentation_charge_sharing_type": "Percentage",
        "mortgage_charge_sharing_type": "Percentage",
        "lender_processing_fees_sharing": 10.0,
        "stamp_duty_sharing": 100.0,
        "documentation_charges_sharing": 100.0,
        "mortgage_charges_sharing": 100.0,
        "doctype": "Lender",
    }

    if not frappe.db.exists("Lender", "Choice Finserv"):
        frappe.get_doc(data).insert()
        frappe.db.commit()
