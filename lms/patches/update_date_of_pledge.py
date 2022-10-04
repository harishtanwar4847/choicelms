from datetime import datetime

import frappe
import requests

import lms


def execute():
    try:
        frappe.reload_doc("Lms", "DocType", "Collateral Ledger")
        frappe.reload_doc("Lms", "DocType", "Loan Application")
        frappe.reload_doc("Lms", "DocType", "Loan")
        collateral_ledger = frappe.get_all(
            "Collateral Ledger",
            filters={"application_doctype": "Loan Application"},
            fields=["*"],
        )
        for i in collateral_ledger:
            collateral_ledger_doc = frappe.get_doc("Collateral Ledger", i.name)
            try:
                if not collateral_ledger_doc.date_of_pledge:
                    collateral_ledger_doc.date_of_pledge = i.creation.date().strftime(
                        "%d-%m-%Y"
                    )
                    collateral_ledger_doc.save(ignore_permissions=True)
                    frappe.db.commit()
                    if i.application_doctype == "Loan Application":
                        application_name = frappe.get_doc(
                            "Loan Application", i.application_name
                        )
                        if application_name.status not in ["Approved", "Rejected"]:
                            for j in application_name.items:
                                if j.isin == collateral_ledger_doc.isin:
                                    j.date_of_pledge = (
                                        collateral_ledger_doc.creation.date().strftime(
                                            "%d-%m-%Y"
                                        )
                                    )
                                    j.save(ignore_permissions=True)
                                    frappe.db.commit()
                    if collateral_ledger_doc.loan:
                        loan = frappe.get_doc("Loan", collateral_ledger_doc.loan)
                        for k in loan.items:
                            if k.isin == collateral_ledger_doc.isin:
                                k.date_of_pledge = (
                                    collateral_ledger_doc.creation.date().strftime(
                                        "%d-%m-%Y"
                                    )
                                )
                                k.save(ignore_permissions=True)
                                frappe.db.commit()

                else:
                    frappe.log_error(
                        message=frappe.get_traceback()
                        + "\nkyc.user {}, PledgeDate = {}".format(i, i.date_of_pledge),
                        title="Else date of pledge",
                    )

            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback()
                    + "\nkyc.user {}PledgeDate = {}".format(i, i.date_of_pledge),
                    title="date of pledge",
                )
    except Exception:
        frappe.log_error(title="date of pledge")
