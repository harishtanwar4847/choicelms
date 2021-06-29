import frappe


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
    return "Apply request successfully submitted."


@frappe.whitelist(allow_guest=True)
def subscribeUpdates(number, email):
    doc = frappe.new_doc("Subscribed for Update")
    doc.number = number
    doc.email = email
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    return "Subscribed successfully."
