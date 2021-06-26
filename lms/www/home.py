import frappe


@frappe.whitelist()
def applyNow(first_name, last_name, emails, mobile):
    print(
        f"\n\n\n\n\n\n==============>>>>>>>>>>>>>Hello world<<<<<<<<<<<<<<=============\n\n\n\n\n\n"
    )
    doc = frappe.new_doc("Apply Request")
    doc.first_name = first_name
    doc.last_name = last_name
    doc.email = emails
    doc.mobile = mobile
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    return "Apply Request successfully Submitted."


@frappe.whitelist()
def subscribeUpdates(number, email):
    print(
        f"\n\n\n\n\n\n==============>>>>>>>>>>>>>Hello world<<<<<<<<<<<<<<=============\n\n\n\n\n\n"
    )
    doc = frappe.new_doc("Subscribed for Update")
    doc.number = number
    doc.email = email
    doc.insert(ignore_permissions=True)
    doc.save()
    frappe.db.commit()
    return "Apply Request successfully Submitted."
