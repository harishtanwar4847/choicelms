import frappe

import lms


@frappe.whitelist(allow_guest=True)
def servercallmethod(loantype, firstname, email, cmobile, message):
    doc = frappe.new_doc("Contact Us Website")
    doc.loantype = loantype
    doc.firstname = firstname
    doc.email = email
    doc.mobile = cmobile
    doc.message = message
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    lms.web_mail("Contact us", doc.firstname, doc.email, "Contact Us")
    return "Contact request submitted successfully."
