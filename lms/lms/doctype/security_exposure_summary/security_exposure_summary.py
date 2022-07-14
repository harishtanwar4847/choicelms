# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SecurityExposureSummary(Document):
    pass


@frappe.whitelist()
def security_exposure_summary():
    try:
        securities = frappe.get_all("Security", fields=["*"])
        for security in securities:
            total_sum = frappe.db.sql(
                """select sum(value) from `tabCollateral Ledger` where loan IS NOT NULL"""
            )
            total_sum = total_sum[0][0]
            qty = frappe.db.sql(
                """select sum(quantity) from `tabCollateral Ledger` where isin = "{}" AND loan IS NOT NULL """.format(
                    security.name
                )
            )
            qty = qty[0][0]
            if not qty:
                qty = 0
            security_exposure_summary = frappe.get_doc(
                dict(
                    doctype="Security Exposure Summary",
                    isin=security.name,
                    security_name=security.security_name,
                    quantity=qty,
                    rate=security.price,
                    value=(qty * security.price),
                    exposure_=((qty * security.price) / total_sum) * 100,
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Exposure Summary"),
        )
