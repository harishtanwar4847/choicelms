import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Allowed Security", force=True)
    # allowed_security_list = frappe.db.get_all("Allowed Security", fields=["*"])
    # for security in allowed_security_list:
    #     security_category = frappe.db.get_value('Security Category', {"category_name": security["security_category"], "lender":security["lender"]},['name'])
    #     allowed_security = frappe.get_doc("Allowed Security", security["name"])
    #     allowed_security.security_category = security_category
    #     allowed_security.save()
    lender_list = frappe.db.get_list("Lender", pluck="name")
    for lender in lender_list:
        frappe.db.sql(
            """
        update
            `tabAllowed Security` ALSC, `tabSecurity Category` SC
        set
            ALSC.security_category = SC.name
        where
            ALSC.security_category = SC.category_name and ALSC.lender = SC.lender
        """.format(
                lender
            )
        )
    frappe.db.commit()
