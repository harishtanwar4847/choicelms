import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "CKYC Identity Details")
    # for prod
    if frappe.utils.get_url() == "https://spark.loans":
        app_Login_Dashboard = "https://bit.ly/3TtaKXr"
        contact_us = "https://bit.ly/3gln78X"
        my_securities = "https://bit.ly/3TAhrXh"
        my_loans = "https://bit.ly/3DacSgE"
    # for new_uat
    elif frappe.utils.get_url() == "https://uat.spark.loans":
        app_Login_Dashboard = "https://bit.ly/3DE6P4A"
        contact_us = "https://bit.ly/3TXzarG"
        my_securities = "https://bit.ly/3FliohZ"
        my_loans = "https://bit.ly/3SFsvBt"
    # for local and dev
    else:
        contact_us = "https://bit.ly/3SdZSez"
        app_Login_Dashboard = "https://bit.ly/3D9zRbZ"
        my_securities = "https://bit.ly/3VEwfFZ"
        my_loans = "https://bit.ly/3TbZCxD"

    las_settings = frappe.get_single("LAS Settings")
    las_settings.app_login_dashboard = app_Login_Dashboard
    las_settings.my_securities = my_securities
    las_settings.my_loans = my_loans
    las_settings.contact_us = contact_us

    las_settings.save(ignore_permissions=True)
    frappe.db.commit()
