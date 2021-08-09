import frappe


def execute():
    contact_us_settings = frappe.get_single("Contact Us Settings")

    contact_us_settings.forward_to_email = "ankit.jain@spark.loans"
    contact_us_settings.save()

    frappe.db.commit()
