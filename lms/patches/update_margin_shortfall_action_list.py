import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Margin Shortfall Action", force=True)
    all_actions = frappe.get_all("Margin Shortfall Action", ["*"])
    if len(all_actions) == 3:
        for a in all_actions:
            frappe.get_doc(
                {
                    "doctype": "Margin Shortfall Action",
                    "max_threshold": a.max_threshold,
                    "instrument_type": "Mutual Fund",
                    "scheme_type": "Debt",
                    "sell_off_after_hours": a.sell_off_after_hours,
                    "sell_off_deadline_eod": a.sell_off_deadline_eod,
                }
            ).insert(ignore_permissions=True)
            frappe.get_doc(
                {
                    "doctype": "Margin Shortfall Action",
                    "max_threshold": a.max_threshold,
                    "instrument_type": "Mutual Fund",
                    "scheme_type": "Equity",
                    "sell_off_after_hours": a.sell_off_after_hours,
                    "sell_off_deadline_eod": a.sell_off_deadline_eod,
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()
