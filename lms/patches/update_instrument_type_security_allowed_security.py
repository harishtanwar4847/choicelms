import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Security")
    frappe.db.sql(
        """update `tabSecurity` set instrument_type = "Shares";
     """
    )
    frappe.reload_doc("Lms", "DocType", "Allowed Security")
    frappe.db.sql(
        """update `tabAllowed Security` set instrument_type = "Shares";
     """
    )
    frappe.db.commit()
