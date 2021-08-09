import frappe


def execute():
    try:
        email_domain = {
            "name": "spark.loans",
            "domain_name": "spark.loans",
            "email_id": "notifications@spark.loans",
            "email_server": "imap.gmail.com",
            "use_imap": 1,
            "use_ssl": 1,
            "incoming_port": "993",
            "attachment_limit": 1,
            "smtp_server": "email-smtp.ap-south-1.amazonaws.com",
            "use_tls": 1,
            "use_ssl_for_outgoing": 0,
            "smtp_port": "587",
            "doctype": "Email Domain",
        }

        frappe.get_doc(email_domain).insert()
        frappe.db.commit()
    except frappe.DuplicateEntryError:
        pass

    # frappe.db.sql("TRUNCATE `tabEmail Account`", auto_commit=1)

    path = frappe.get_app_path("lms", "patches", "imports", "email_account.csv")
    frappe.core.doctype.data_import.data_import.import_file(
        "Email Account", path, "Insert", console=True
    )
