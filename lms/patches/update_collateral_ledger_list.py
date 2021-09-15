import frappe


def execute():
    collateral_ledgers = frappe.get_all("Collateral Ledger", fields=["*"])
    for collateral_ledger in collateral_ledgers:
        frappe.db.sql("""update `tabCollateral Ledger` set price = (select price from `tabSecurity` where name = '{}'), value = {} *(select price from `tabSecurity` where name = '{}') 
         """.format(collateral_ledger.isin, collateral_ledger.quantity, collateral_ledger.isin))
    frappe.db.commit()
