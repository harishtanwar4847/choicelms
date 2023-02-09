import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Collateral Ledger", force=True)
    collateral_ledgers = frappe.get_all("Collateral Ledger", fields=["*"])
    for collateral_ledger in collateral_ledgers:
        frappe.db.sql(
            """update `tabCollateral Ledger` set price = (select price from `tabSecurity` where name = '{isin}'), value = {qty} *(select price from `tabSecurity` where name = '{isin}'), security_name = (select security_name from `tabSecurity` where name = '{isin}'),security_category = (select security_category from `tabAllowed Security` where isin = '{isin}' and lender = '{lender}') where name = '{name}'
         """.format(
                isin=collateral_ledger.isin,
                qty=collateral_ledger.quantity,
                name=collateral_ledger.name,
                lender=collateral_ledger.lender,
            )
        )
        frappe.db.commit()
