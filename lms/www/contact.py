import frappe


@frappe.whitelist()
def servercallmethod(loantype, firstname, email, cmobile, message):
    print(
        f"\n\n\n\n\n\n==============>>>>>>>>>>>>>Hello world<<<<<<<<<<<<<<=============\n\n\n\n\n\n"
    )
    doc = frappe.new_doc("Contact Us Website")
    doc.loantype = loantype
    doc.firstname = firstname
    doc.email = email
    doc.mobile = cmobile
    doc.message = message
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    return "Apply Request successfully Submitted."
