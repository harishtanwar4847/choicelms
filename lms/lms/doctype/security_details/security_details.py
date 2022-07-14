# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SecurityDetails(Document):
    pass


@frappe.whitelist()
def security_details():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            customer = frappe.get_doc("Loan Customer", loan.customer)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            loan_application = frappe.get_all(
                "Loan Application",
                filters={"customer": loan.customer},
                fields=["pledgor_boid"],
            )
            pledgor_boid = loan_application[0].pledgor_boid
            collateral_ledger = frappe.get_all(
                "Collateral Ledger", filters={"loan": loan.name}, fields=["*"]
            )
            for i in collateral_ledger:
                co_ledger = i
            security_details = frappe.get_doc(
                dict(
                    doctype="Security Details",
                    loan_no=loan.name,
                    client_name=loan.customer_name,
                    security_category=co_ledger.security_category,
                    isin=co_ledger.isin,
                    security_name=co_ledger.security_name,
                    quantity=co_ledger.quantity,
                    rate=co_ledger.price,
                    value=co_ledger.value,
                    pledgor_boid=pledgor_boid,
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Details"),
        )
