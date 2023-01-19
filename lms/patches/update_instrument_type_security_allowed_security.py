import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Security", force=True)
    frappe.db.sql(
        """update `tabSecurity` set instrument_type = "Shares";
     """
    )
    frappe.reload_doc("Lms", "DocType", "Allowed Security", force=True)
    frappe.db.sql(
        """update `tabAllowed Security` set instrument_type = "Shares";
     """
    )
    frappe.db.commit()
