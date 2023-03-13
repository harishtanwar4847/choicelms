from datetime import datetime

import frappe
import requests

import lms


def execute():
    try:
        frappe.reload_doc("Lms", "DocType", "Loan")
        collateral_ledger = frappe.get_all(
            "Collateral Ledger",
            filters={"application_doctype": "Loan Application"},
            fields=["*"],
        )
        for i in collateral_ledger:
            collateral_ledger_doc = frappe.get_doc("Collateral Ledger", i.name)
            try:
                if collateral_ledger_doc.loan:
                    loan = frappe.get_doc("Loan", collateral_ledger_doc.loan)
                    for j in loan.items:
                        if j.isin == collateral_ledger_doc.isin:
                            j.psn = collateral_ledger_doc.psn
                            j.save(ignore_permissions=True)
                            frappe.db.commit()

            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback()
                    + "\nloan{}psn = {}".format(i, i.psn),
                    title="PSN",
                )
    except Exception:
        frappe.log_error(title="PSN")
