import frappe


def execute():
    collateral_ledgers = frappe.get_all("Collateral Ledger", fields=["*"])
    for collateral_ledger in collateral_ledgers:
        security = frappe.get_doc("Security", filters = {"isin": collateral_ledger.isin})
        collateral_ledger.category = security.category
        collateral_ledger.price = security.price
        collateral_ledger.value = security.price * collateral_ledger.quantity
        collateral_ledger.save()
    frappe.db.commit()
