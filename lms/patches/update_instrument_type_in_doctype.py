import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Cart", force=True)
    frappe.reload_doc("Lms", "DocType", "Loan Application", force=True)
    frappe.reload_doc("Lms", "DocType", "Loan", force=True)
    frappe.reload_doc("Lms", "DocType", "Loan Transaction", force=True)
    frappe.reload_doc("Lms", "DocType", "Loan Margin Shortfall", force=True)
    frappe.reload_doc("Lms", "DocType", "Margin Shortfall Action", force=True)
    frappe.reload_doc("Lms", "DocType", "Collateral Ledger", force=True)
    frappe.reload_doc("Lms", "DocType", "Top up Application", force=True)

    frappe.db.sql("""update `tabCart` set instrument_type = "Shares";""")
    frappe.db.sql("""update `tabLoan Application` set instrument_type = "Shares";""")
    frappe.db.sql("""update `tabLoan` set instrument_type = "Shares";""")
    frappe.db.sql("""update `tabLoan Transaction` set instrument_type = "Shares";""")
    frappe.db.sql(
        """update `tabLoan Margin Shortfall` set instrument_type = "Shares";"""
    )
    frappe.db.sql(
        """update `tabMargin Shortfall Action` set instrument_type = "Shares";"""
    )
    frappe.db.sql("""update `tabCollateral Ledger` set instrument_type = "Shares";""")
    frappe.db.sql("""update `tabTop up Application` set instrument_type = "Shares";""")
    frappe.db.commit()
