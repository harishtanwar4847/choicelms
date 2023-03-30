import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Allowed Security")
    cat = frappe.get_all("Allowed Security", fields=["*"])
    for i in cat:
        doc = frappe.get_doc("Allowed Security", i.name)
        category = i.security_category.split("_")[0]
        frappe.db.set_value("Allowed Security", doc.name, "category_name", category)
        frappe.db.commit()
