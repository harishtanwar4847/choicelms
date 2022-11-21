import frappe


def execute():
    frappe.reload_doc("Lms", "DocType", "Unpledge Application")
    frappe.reload_doc("Lms", "DocType", "Unpledge Application Item")
    frappe.reload_doc("Lms", "DocType", "Sell Collateral Application")
    frappe.reload_doc("Lms", "DocType", "Sell Collateral Application Item")
    unpledeg_application_item = frappe.get_all(
        "Unpledge Application Item", fields=["*"]
    )
    for i in unpledeg_application_item:
        eligible_percentage = frappe.get_all(
            "Allowed Security", filters={"isin": i.isin}, fields=["eligible_percentage"]
        )
        frappe.db.set_value(
            "Unpledge Application Item",
            i.name,
            "eligible_percentage",
            eligible_percentage[0].eligible_percentage,
        )
        frappe.db.commit()

    sell_collateral_application_item = frappe.get_all(
        "Sell Collateral Application Item", fields=["*"]
    )
    for i in sell_collateral_application_item:
        eligible_percentage = frappe.get_all(
            "Allowed Security", filters={"isin": i.isin}, fields=["eligible_percentage"]
        )
        frappe.db.set_value(
            "Sell Collateral Application Item",
            i.name,
            "eligible_percentage",
            eligible_percentage[0].eligible_percentage,
        )
        frappe.db.commit()
