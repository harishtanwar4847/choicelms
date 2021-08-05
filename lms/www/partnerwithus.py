import frappe

import lms


@frappe.whitelist(allow_guest=True)
def applyNowPartner(pfirstname, plastname, pemail, pmobile, pmessage):
    doc = frappe.new_doc("Partner with Us")
    doc.pfirstname = pfirstname
    doc.plastname = plastname
    doc.pemail = pemail
    doc.pmobile = pmobile
    doc.pmessage = pmessage
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    full_name = doc.pfirstname + " " + doc.plastname
    lms.web_mail("Partner with Us", full_name, doc.pemail, "Partner with Us")
    return "Partner with Us Request successfully Submitted."
