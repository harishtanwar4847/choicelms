import frappe


def execute():
    consents = [
        {
            "doctype": "Consent",
            "name": "E-sign",
            "consent": """By Clicking on Yes, I authorise Spark Financial Technologies Private Limited to - 

1.  Use my Aadhaar / Virtual ID details (as applicable) for eSigning of documents for opening loan account through Spark Financial Technologies Private Limited and authenticate my identity through the Aadhaar Authentication system (Aadhaar based e-KYC services of UIDAI) in accordance with the provisions of the Aadhaar (Targeted Delivery of Financial and other Subsidies, Benefits and Services) Act, 2016 and the allied rules and regulations notified thereunder and for no other purpose. 

2.  Authenticate my Aadhaar / Virtual ID through OTP or Biometric for authenticating my identity through the Aadhaar Authentication system for obtaining my e-KYC through Aadhaar based e-KYC services of UIDAI and use my Photo and Demographic details (Name, Gender, Date of Birth and Address) for eSigning of documents for opening trading account or demat account or both the accounts for/with Choice Equity Broking Private Limited. 

3.  I understand that Security and confidentiality of personal identity data provided, for the purpose of Aadhaar based authentication is ensured by NSDL e-Gov and the data will be stored by NSDL e-Gov till such time as mentioned in guidelines from UIDAI from time to time.""",
        },
        {
            "doctype": "Consent",
            "name": "Kyc",
            "consent": "I allow my data to be collected from my DP (Demat Account).",
        },
        {
            "doctype": "Consent",
            "name": "Login",
            "consent": "I agree to accept terms of use and privacy policy",
        },
    ]

    frappe.db.sql("TRUNCATE `tabConsent`")

    for consent_data in consents:
        frappe.get_doc(consent_data).insert()

    frappe.db.commit()
