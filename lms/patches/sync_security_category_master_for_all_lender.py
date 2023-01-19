import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Security Category", force=True)

    doc_exists = frappe.db.sql(
        "SELECT EXISTS(SELECT 1 FROM `tabSecurity Category`) as OUTPUT;",
        as_dict=True,
    )

    if not doc_exists[0].get("OUTPUT"):
        lender_list = frappe.db.get_list("Lender", pluck="name")
        frappe.get_doc(
            {
                "doctype": "Security Category",
                "lender": "Choice Finserv",
                "category_name": "Cat D",
            }
        ).insert()
        for lender in lender_list:
            allowed_security_list = frappe.db.sql(
                'select distinct security_category from `tabAllowed Security` where lender = "{lender}"'.format(
                    lender=lender
                ),
                as_dict=True,
            )
            if allowed_security_list:
                for allowed_security in allowed_security_list:
                    frappe.get_doc(
                        {
                            "doctype": "Security Category",
                            "lender": lender,
                            "category_name": allowed_security["security_category"],
                        }
                    ).insert()
                frappe.db.commit()
