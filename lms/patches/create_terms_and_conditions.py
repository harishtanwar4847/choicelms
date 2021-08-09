import frappe


def execute():
    tnc = [
        "I hereby irrevocably and unconditionally authorise Spark.loans, its lending partner and my DP to notify NSDL/ CDSL/ CAMS through a system to system  communication the aforesaid securities for NSDL/ CDSL/ CAMS to forthwith thereupon pledge / mark lien on the securities requested for pledge / marking lien in favour of the lender(s) for securing the LAS facility.",
        "I agree to consent to call for marketing and promotional activities",
        "I Confirm the above application for Loan Against Securities (LAS) Facility.",
    ]

    frappe.db.sql("TRUNCATE `tabTerms and Conditions`")

    for condition in tnc:
        frappe.get_doc(
            {"doctype": "Terms and Conditions", "tnc": condition, "is_active": True}
        ).insert()

    frappe.db.commit()
