# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SecurityTransaction(Document):
    pass


@frappe.whitelist()
def security_transaction():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            collateral_ledger = frappe.get_all(
                "Collateral Ledger", filters={"loan": loan.name}, fields=["*"]
            )
            for i in collateral_ledger:
                if i.request_type != "Pledge":
                    qty = -(i.quantity)
                else:
                    qty = i.quantity
                security_transaction = frappe.get_doc(
                    dict(
                        doctype="Security Transaction",
                        loan_no=loan.name,
                        client_name=loan.customer_name,
                        date=i.creation.date(),
                        request_type=i.request_type,
                        isin=i.isin,
                        security_name=i.security_name,
                        psn=i.psn,
                        qty=qty,
                        rate=i.price,
                        value=i.value,
                    ),
                ).insert(ignore_permissions=True)
                frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Transaction"),
        )
