import frappe

import lms


@frappe.whitelist(allow_guest=True)
def applyNow(first_name, last_name, emails, mobile):
    doc = frappe.new_doc("Apply Request")
    doc.first_name = first_name
    doc.last_name = last_name
    doc.email = emails
    doc.mobile = mobile
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    full_name = doc.first_name + " " + doc.last_name
    lms.web_mail("Apply Now", full_name, doc.email, "Apply Now")
    return "Apply request successfully submitted."


@frappe.whitelist(allow_guest=True)
def subscribeUpdates(number, email):
    doc = frappe.new_doc("Subscribed for Update")
    doc.number = number
    doc.email = email
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    lms.web_mail(
        "Subscribe for Updates", "Subscriber", doc.email, "Subscribe for updates"
    )
    return "Subscribed successfully."


def get_context(context):
    context.lenders = frappe.get_all(
        "Lender", fields=["name", "logo_file_1", "lender_title"], order_by="creation"
    )
