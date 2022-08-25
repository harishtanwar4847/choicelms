# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ClientSanctionDetails(Document):
    pass


@frappe.whitelist()
def client_sanction_details():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            customer = frappe.get_doc("Loan Customer", loan.customer)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            interest_config = frappe.get_value(
                "Interest Configuration",
                {
                    "to_amount": [">=", loan.sanctioned_limit],
                },
                order_by="to_amount asc",
            )
            int_config = frappe.get_doc("Interest Configuration", interest_config)
            roi_ = int_config.base_interest * 12
            start_date = frappe.db.sql(
                """select cast(creation as date) from `tabLoan` where name = "{}" """.format(
                    loan.name
                )
            )
            client_sanction_details = frappe.get_doc(
                dict(
                    doctype="Client Sanction Details",
                    client_code=customer.name,
                    loan_no=loan.name,
                    client_name=loan.customer_name,
                    pan_no=user_kyc.pan_no,
                    start_date=start_date,
                    end_date=loan.expiry_date,
                    sanctioned_amount=loan.sanctioned_limit,
                    roi=roi_,
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Client Sanction Details"),
        )
