import frappe


@frappe.whitelist(allow_guest=True)
def applyNowPartner(pfirstname, plastname, pemail, pmobile, pmessage):
    print(
        f"\n\n\n\n\n\n==============>>>>>>>>>>>>>Hello world<<<<<<<<<<<<<<=============\n\n\n\n\n\n"
    )
    doc = frappe.new_doc("Partner with Us")
    doc.pfirstname = pfirstname
    doc.plastname = plastname
    doc.pemail = pemail
    doc.pmobile = pmobile
    doc.pmessage = pmessage
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    return "Partner with Us Request successfully Submitted."
